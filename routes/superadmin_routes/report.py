from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for, current_app, abort
from flask_login import login_required, current_user
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
from models import SensorData, Device, Parameter, Company, DashboardSensor, Dashboard, UserDashboard, NavigationSettings
from sqlalchemy import or_, and_
from types import SimpleNamespace
from datetime import datetime
from .report_pdf import PDFReportGenerator
from extensions import db  # Import db from your extensions module
from .report_excel import ExcelReportGenerator


report_bp = Blueprint('report_bp', __name__, url_prefix='/reports')


def get_dashboard_devices_for_reports(dashboard_id, user):
    """
    Get devices accessible to user for a specific dashboard based on dashboard→sensor allocation.
    
    Rules:
    1. User must be assigned to dashboard via user_dashboards (except super_admin)
    2. Dashboard must have at least one sensor in dashboard_sensors
    3. Returns devices from dashboard_sensors table
    
    Returns:
        tuple: (devices, error_message) - devices is list of Device objects or None on error
    """
    # Validate dashboard exists
    dashboard = Dashboard.query.get(dashboard_id)
    if not dashboard:
        return None, "Dashboard not found"
    
    # Check if dashboard has sensors
    has_sensors = db.session.query(DashboardSensor).filter(
        DashboardSensor.dashboard_id == dashboard_id
    ).first()
    
    if not has_sensors:
        return [], "This dashboard has no sensors allocated"
    
    # Check user access to dashboard (super_admin can access any dashboard)
    if user.role != 'super_admin':
        user_access = db.session.query(UserDashboard).filter(
            UserDashboard.user_id == user.id,
            UserDashboard.dashboard_id == dashboard_id
        ).first()
        
        if not user_access:
            return None, "You do not have access to this dashboard"
    
    # Get all device IDs from dashboard_sensors for this dashboard
    dashboard_device_ids = db.session.query(DashboardSensor.device_id).filter(
        DashboardSensor.dashboard_id == dashboard_id
    ).all()
    
    if not dashboard_device_ids:
        return [], "No devices found for this dashboard"
    
    # Extract device IDs
    device_ids = [device_id[0] for device_id in dashboard_device_ids]
    
    # Get device objects (ignore device ownership completely)
    devices = Device.query.filter(Device.id.in_(device_ids)).all()
    
    return devices, None


@report_bp.route('/', methods=['GET', 'POST'])
@login_required
def reports():
    """Generate sensor reports - access controlled by dashboard→sensor allocation"""
    
    # All roles can access if they have dashboard access
    if current_user.role not in ['admin', 'super_admin', 'user']:
        return "Access denied", 403
    
    # Get dashboard_id from request - try both GET and POST methods
    if request.method == 'GET':
        dashboard_id = request.args.get('dashboard_id', type=int)
    else:  # POST method
        dashboard_id = request.form.get('dashboard_id', type=int)
    
    # If no dashboard_id in request, check if we can get it from referrer or session
    if not dashboard_id:
        # Try to get dashboard_id from session or other context
        # This is a fallback for when users click on Reports without proper parameters
        flash('Please select a dashboard first, then access Reports from within that dashboard.', 'error')
        # Redirect to dashboard selection page
        return redirect(url_for('dashboard.dashboard_list'))
    
    # ------------------ GET REQUEST ------------------
    if request.method == 'GET':
        # Get devices based on dashboard allocation (ignores device ownership)
        devices, error = get_dashboard_devices_for_reports(dashboard_id, current_user)
        
        if error:
            if "access" in error.lower() or "not found" in error.lower():
                flash(error, 'error')
                return redirect(url_for('dashboard.dashboard_list'))
            elif "no sensors" in error.lower():
                flash(error, 'warning')
                # Still show page but with empty devices list
                devices = []
            else:
                flash(error, 'error')
        
        # Get user's dashboards for navigation
        if current_user.role == 'super_admin':
            user_dashboards = Dashboard.query.all()
        else:
            user_dashboard_ids = db.session.query(UserDashboard.dashboard_id).filter(
                UserDashboard.user_id == current_user.id
            ).all()
            dashboard_ids = [dash_id[0] for dash_id in user_dashboard_ids]
            user_dashboards = Dashboard.query.filter(Dashboard.id.in_(dashboard_ids)).all() if dashboard_ids else []
        
        # Get navigation settings
        nav_settings = db.session.query(NavigationSettings).filter(
            NavigationSettings.dashboard_id == dashboard_id
        ).first()
        
        if nav_settings:
            navigation_settings = SimpleNamespace(
                dashboard_management=nav_settings.dashboard_management,
                reports=nav_settings.reports,
                analytics=nav_settings.analytics,
                download=nav_settings.download,
                support=nav_settings.support,
                settings=nav_settings.settings
            )
        else:
            navigation_settings = SimpleNamespace(
                dashboard_management=True,
                reports=True,
                analytics=True,
                download=True,
                support=True,
                settings=True
            )
        
        return render_template(
            'dashboard/reports.html',
            devices=devices or [],  # Pass empty list on error
            user_role=current_user.role,
            navigation_settings=navigation_settings,
            dashboard_id=dashboard_id,
            user_dashboards=user_dashboards
        )
    
    # ------------------ POST REQUEST (Generate PDF) ------------------
    elif request.method == 'POST':
        # Validate CSRF token
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            flash('CSRF token validation failed. Please try again.', 'error')
            return redirect(request.referrer or url_for('report_bp.reports'))
        
        # Get dashboard_id from form
        dashboard_id = request.form.get('dashboard_id', type=int)
        
        if not dashboard_id:
            flash('Dashboard ID is required', 'error')
            # Try to redirect back with dashboard_id from referrer
            if request.referrer and 'dashboard_id=' in request.referrer:
                import re
                match = re.search(r'dashboard_id=(\d+)', request.referrer)
                if match:
                    return redirect(url_for('report_bp.reports', dashboard_id=int(match.group(1))))
            return redirect(url_for('dashboard.dashboard_list'))
        
        selected_ids = request.form.getlist('device_ids[]')
        if not selected_ids:
            flash('No devices selected', 'error')
            return redirect(url_for('report_bp.reports', dashboard_id=dashboard_id))
        
        # PREVENT TAMPERING: Validate selected devices against dashboard sensors
        dashboard_device_ids = db.session.query(DashboardSensor.device_id).filter(
            DashboardSensor.dashboard_id == dashboard_id
        ).all()
        
        valid_device_ids = {device_id[0] for device_id in dashboard_device_ids}
        selected_ids = [int(device_id) for device_id in selected_ids 
                       if int(device_id) in valid_device_ids]
        
        if not selected_ids:
            flash('Selected devices are not allocated to this dashboard', 'error')
            return redirect(url_for('report_bp.reports', dashboard_id=dashboard_id))
        
        # Verify user has access to dashboard (redundant check for security)
        if current_user.role != 'super_admin':
            user_access = db.session.query(UserDashboard).filter(
                UserDashboard.user_id == current_user.id,
                UserDashboard.dashboard_id == dashboard_id
            ).first()
            
            if not user_access:
                flash('Access denied to this dashboard', 'error')
                return redirect(url_for('dashboard.dashboard_list'))
        
        # Get time range from form
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        start_date = datetime.fromisoformat(start_date_str) if start_date_str else None
        end_date = datetime.fromisoformat(end_date_str) if end_date_str else None
        
        try:
            print(f"Starting report generation for {len(selected_ids)} devices")
            
            # Query selected devices - NO ownership filter, only dashboard allocation
            devices = Device.query.filter(Device.id.in_(selected_ids)).limit(10).all()
            
            if not devices:
                flash('No valid devices found', 'error')
                return redirect(url_for('report_bp.reports', dashboard_id=dashboard_id))
            
            print(f"Found {len(devices)} devices to process")
            
            # Get company ID
            company_id = devices[0].company_id if devices[0].company_id else current_user.company_id
            
            # Generate PDF report
            pdf_generator = PDFReportGenerator()
            buffer = pdf_generator.generate_device_report(
                devices=devices,
                company_id=company_id,
                start_date=start_date,
                end_date=end_date
            )
            
            # Create filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"Device_Report_{timestamp}.pdf"
            
            print(f"PDF generated successfully, file size: {buffer.getbuffer().nbytes} bytes")
            
            return send_file(buffer, as_attachment=True, download_name=filename)
            
        except Exception as e:
            print(f"Error in report generation: {str(e)}")
            flash(f'Error generating report: {str(e)}', 'error')
            return redirect(url_for('report_bp.reports', dashboard_id=dashboard_id))


@report_bp.route('/excel', methods=['POST'])
@login_required
def download_excel_report():
    """Generate sensor report in Excel format - access controlled by dashboard→sensor allocation"""
    
    # All roles can access if they have dashboard access
    if current_user.role not in ['admin', 'super_admin', 'user']:
        return "Access denied", 403
    
    # =========================
    # CSRF Validation
    # =========================
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('CSRF token validation failed.', 'error')
        # Try to redirect back with dashboard_id if available
        if request.referrer and 'dashboard_id=' in request.referrer:
            import re
            match = re.search(r'dashboard_id=(\d+)', request.referrer)
            if match:
                return redirect(url_for('report_bp.reports', dashboard_id=int(match.group(1))))
        return redirect(url_for('report_bp.reports'))
    
    # =========================
    # Form Inputs
    # =========================
    dashboard_id = request.form.get('dashboard_id', type=int)
    
    if not dashboard_id:
        flash('Dashboard ID is required', 'error')
        # Try to redirect back with dashboard_id from referrer
        if request.referrer and 'dashboard_id=' in request.referrer:
            import re
            match = re.search(r'dashboard_id=(\d+)', request.referrer)
            if match:
                return redirect(url_for('report_bp.reports', dashboard_id=int(match.group(1))))
        return redirect(url_for('dashboard.dashboard_list'))
    
    selected_ids = request.form.getlist('device_ids[]')
    time_interval = request.form.get('time_interval')
    
    if not selected_ids:
        flash('No devices selected', 'error')
        return redirect(url_for('report_bp.reports', dashboard_id=dashboard_id))
    
    # =========================
    # Dashboard Access Check
    # =========================
    if current_user.role != 'super_admin':
        user_access = db.session.query(UserDashboard).filter(
            UserDashboard.user_id == current_user.id,
            UserDashboard.dashboard_id == dashboard_id
        ).first()
        
        if not user_access:
            flash('Access denied to this dashboard', 'error')
            return redirect(url_for('dashboard.dashboard_list'))
    
    # =========================
    # PREVENT TAMPERING: Validate selected devices against dashboard sensors
    # =========================
    dashboard_device_ids = db.session.query(
        DashboardSensor.device_id
    ).filter(
        DashboardSensor.dashboard_id == dashboard_id
    ).all()
    
    valid_ids = {d[0] for d in dashboard_device_ids}
    selected_ids = [int(d) for d in selected_ids if int(d) in valid_ids]
    
    if not selected_ids:
        flash('Selected devices are not allocated to this dashboard', 'error')
        return redirect(url_for('report_bp.reports', dashboard_id=dashboard_id))
    
    # =========================
    # Time Interval Validation
    # =========================
    if time_interval and time_interval != "":
        ALLOWED_INTERVALS = [
            "",
            "1 minute",
            "5 minutes", 
            "1 hour",
            "6 hours",
            "1 day"
        ]
        
        if time_interval not in ALLOWED_INTERVALS:
            flash('Invalid time interval selected', 'error')
            return redirect(url_for('report_bp.reports', dashboard_id=dashboard_id))
    
    # =========================
    # Date Range
    # =========================
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    start_date = datetime.fromisoformat(start_date) if start_date else None
    end_date = datetime.fromisoformat(end_date) if end_date else None
    
    # =========================
    # Device Access - NO ownership filter
    # =========================
    devices = Device.query.filter(Device.id.in_(selected_ids)).all()
    
    if not devices:
        flash('No devices found', 'error')
        return redirect(url_for('report_bp.reports', dashboard_id=dashboard_id))
    
    company_id = devices[0].company_id or current_user.company_id
    
    # =========================
    # Excel Generation
    # =========================
    excel_generator = ExcelReportGenerator()
    
    buffer = excel_generator.generate_device_report(
        devices=devices,
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
        file_type="excel",
        time_interval=time_interval if time_interval else None
    )
    
    # =========================
    # File Name
    # =========================
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if time_interval and time_interval != "":
        # Create filename-friendly interval label
        interval_map = {
            "1 minute": "1min",
            "5 minutes": "5min",
            "1 hour": "1hr",
            "6 hours": "6hr",
            "1 day": "1day"
        }
        interval_label = interval_map.get(time_interval, "avg")
        filename = f"Device_Report_{interval_label}_{timestamp}.xlsx"
    else:
        filename = f"Device_Report_{timestamp}.xlsx"
    
    # =========================
    # Send File
    # =========================
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )