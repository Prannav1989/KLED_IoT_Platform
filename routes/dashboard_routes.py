# routes/dashboard_routes.py
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_wtf.csrf import validate_csrf
from sqlalchemy import and_, or_
from extensions import db
from models import User, Device, Dashboard, Company, DashboardSensor, UserDashboard, SensorData,NavigationSettings,Parameter,UserDevice
from sqlalchemy import func
from datetime import datetime




dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

def get_accessible_dashboards(user):
    """Get all dashboards accessible to the current user based on role"""
    if user.role == 'super_admin':
        return Dashboard.query.all()
    elif user.role == 'admin':
        # Handle the string company_id
        if isinstance(user.company_id, int):
            company_id = int(user.company_id)
            return Dashboard.query.filter(
                or_(
                    Dashboard.company_id == company_id,
                    Dashboard.created_by == user.id
                )
            ).all()
        else:
            return Dashboard.query.filter(Dashboard.created_by == user.id).all()
    elif user.role == 'user':
        return Dashboard.query.join(UserDashboard).filter(
            UserDashboard.user_id == user.id
        ).all()
    else:
        return []
    

from zoneinfo import ZoneInfo

def to_ist(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("Asia/Kolkata"))


def get_accessible_parameters(user, company_id=None, target_user_id=None):
    """Get parameters accessible to the current user based on role.
    Optionally filter by company_id and assigned user (target_user_id)."""
    
    query = Parameter.query.join(Device)
    
    if user.role == 'super_admin':
        # Filter by company if provided
        if company_id:
            query = query.filter(Device.company_id == company_id)
        # Filter by user if provided
        if target_user_id:
            query = query.filter(Device.user_id == target_user_id)
        return query.all()
    
    elif user.role == 'admin':
        # Admin can only see parameters in their own company
        if isinstance(user.company_id, int):
            user_company_id = int(user.company_id)
            query = query.filter(Device.company_id == user_company_id)
            # Optional: filter by a specific user within the company
            if target_user_id:
                query = query.filter(Device.user_id == target_user_id)
            return query.all()
        return []
    
    elif user.role == 'user':
        # Users see only parameters from devices assigned to dashboards they have access to
        user_dashboard_ids = [
            ud.dashboard_id for ud in UserDashboard.query.filter_by(user_id=user.id).all()
        ]
        dashboard_device_ids = [
            ds.device_id for ds in DashboardSensor.query.filter(
                DashboardSensor.dashboard_id.in_(user_dashboard_ids)
            ).all()
        ]
        return Parameter.query.filter(Parameter.device_id.in_(dashboard_device_ids)).all()
    
    return []

def get_accessible_devices(user, company_id=None, target_user_id=None):
    """Get devices accessible to the current user based on role.
    Optionally filter by company_id and assigned user (target_user_id)."""
    
    query = Device.query
    
    if user.role == 'super_admin':
        # Filter by company if provided
        if company_id:
            query = query.filter(Device.company_id == company_id)
        # Filter by user if provided
        if target_user_id:
            query = query.filter(Device.user_id == target_user_id)
        return query.all()
    
    elif user.role == 'admin':
        # Admin can only see devices in their own company
        if isinstance(user.company_id, int):
            user_company_id = int(user.company_id)
            query = query.filter(Device.company_id == user_company_id)
            # Optional: filter by a specific user within the company
            if target_user_id:
                query = query.filter(Device.user_id == target_user_id)
            return query.all()
        return []
    
    elif user.role == 'user':
        # Users see only devices assigned to dashboards they have access to
        user_dashboard_ids = [
            ud.dashboard_id for ud in UserDashboard.query.filter_by(user_id=user.id).all()
        ]
        dashboard_device_ids = [
            ds.device_id for ds in DashboardSensor.query.filter(
                DashboardSensor.dashboard_id.in_(user_dashboard_ids)
            ).all()
        ]
        return Device.query.filter(Device.id.in_(dashboard_device_ids)).all()
    
    return []



@dashboard_bp.route('/')
@login_required
def dashboard_list():
    """Display list of accessible dashboards"""

    dashboards = get_accessible_dashboards(current_user)
    dashboard_stats = {}

    dashboard_ids = [d.id for d in dashboards]

    # -------------------------------
    # PRELOAD DASHBOARD → DEVICE MAP
    # -------------------------------
    dashboard_device_map = {}

    if dashboard_ids:
        dashboard_sensors = DashboardSensor.query.filter(
            DashboardSensor.dashboard_id.in_(dashboard_ids)
        ).all()

        for ds in dashboard_sensors:
            dashboard_device_map.setdefault(ds.dashboard_id, set()).add(ds.device_id)

    # ===============================
    # DASHBOARD LEVEL STATS
    # ===============================
    for d in dashboards:
        device_ids = dashboard_device_map.get(d.id, set())

        if device_ids:
            # IoT Sensors count (devices)
            iot_sensor_count = Device.query.filter(
                Device.id.in_(device_ids),
                Device.company_id == current_user.company_id
            ).distinct().count()

            # Parameters count
            parameter_count = Parameter.query.join(Device).filter(
                Parameter.device_id.in_(device_ids),
                Device.company_id == current_user.company_id
            ).count()
        else:
            iot_sensor_count = 0
            parameter_count = 0

        dashboard_stats[d.id] = {
            "iot_sensor_count": iot_sensor_count,
            "parameter_count": parameter_count,
            "device_ids": list(device_ids)
        }

    # ==================================================
    # SUPER ADMIN DASHBOARD
    # ==================================================
    if current_user.role == "super_admin":
        companies = Company.query.all()
        active_dashboards = Dashboard.query.count()
        total_admins = User.query.filter_by(role="admin").count()

        total_iot_sensors = Device.query.count()
        total_parameters = Parameter.query.count()

        return render_template(
            "dashboard/super_admin_dashboards.html",
            dashboards=dashboards,
            companies=companies,
            dashboard_stats=dashboard_stats,
            active_dashboards=active_dashboards,
            total_admins=total_admins,
            total_iot_sensors=total_iot_sensors,
            total_parameters=total_parameters
        )

    # ==================================================
    # ADMIN DASHBOARD
    # ==================================================
    elif current_user.role == "admin":
        company = None
        users = []
        total_iot_sensors = 0
        total_parameters = 0
        active_dashboards = 0

        if current_user.company_id:
            company_id = current_user.company_id
            company = Company.query.get(company_id)

            if company:
                # Users under this company
                users = User.query.filter(
                    User.company_id == company_id,
                    User.role == "user"
                ).all()

                # All dashboards for company
                company_dashboards = Dashboard.query.filter_by(
                    company_id=company_id
                ).all()

                active_dashboards = len(company_dashboards)

                # Collect all assigned device IDs
                all_device_ids = set()
                for d in company_dashboards:
                    all_device_ids.update(dashboard_device_map.get(d.id, set()))

                if all_device_ids:
                    total_iot_sensors = Device.query.filter(
                        Device.id.in_(all_device_ids),
                        Device.company_id == company_id
                    ).distinct().count()

                    total_parameters = Parameter.query.join(Device).filter(
                        Parameter.device_id.in_(all_device_ids),
                        Device.company_id == company_id
                    ).count()

        return render_template(
            "admin/admin_dashboard.html",
            dashboards=dashboards,
            company=company,
            users=users,
            total_iot_sensors=total_iot_sensors,
            total_parameters=total_parameters,
            active_dashboards=active_dashboards,
            dashboard_stats=dashboard_stats
        )

    # ==================================================
    # USER DASHBOARD
    # ==================================================
    else:
        # Devices explicitly assigned to user
        user_device_ids = db.session.query(UserDevice.device_id).filter(
            UserDevice.user_id == current_user.id
        )

        # Devices assigned via dashboards
        dashboard_device_ids = set()
        for d in dashboards:
            dashboard_device_ids.update(dashboard_device_map.get(d.id, set()))

        # Final allowed devices
        allowed_device_ids = set(user_device_ids).intersection(dashboard_device_ids)

        total_iot_sensors = len(allowed_device_ids)

        total_parameters = 0
        if allowed_device_ids:
            total_parameters = Parameter.query.filter(
                Parameter.device_id.in_(allowed_device_ids)
            ).count()

        return render_template(
            "user_dashboard/dashboard.html",
            dashboards=dashboards,
            dashboard_stats=dashboard_stats,
            total_iot_sensors=total_iot_sensors,
            total_parameters=total_parameters,
            user=current_user
        )


@dashboard_bp.route('/company/<int:company_id>')
@login_required
def company_dashboard(company_id):
    """Super admin view of a specific company's dashboards"""
    if current_user.role != 'super_admin':
        flash('Access denied. Super admin privileges required.', 'error')
        return redirect(url_for('dashboard.dashboard_list'))
    
    company = Company.query.get_or_404(company_id)

    # All dashboards for this company
    dashboards = Dashboard.query.filter_by(company_id=company_id).all()

    # All users for this company - match by string company_id
    users = User.query.filter_by(company_id=str(company_id)).all()

    # All admins
    admins = User.query.filter_by(company_id=str(company_id), role='admin').all()

    # Count total parameters for this company (replacing total_sensors)
    total_parameters = Parameter.query.join(Device).filter(Device.company_id == company_id).count()

    # Count total devices for this company (useful additional metric)
    total_devices = Device.query.filter(Device.company_id == company_id).count()

    # Count active dashboards
    active_dashboards = Dashboard.query.filter_by(company_id=company_id).count()

    return render_template(
        'dashboard/company_dashboard.html',
        company=company,
        dashboards=dashboards,
        users=users,
        admins=admins,
        total_parameters=total_parameters,  # Changed from total_sensors
        total_devices=total_devices,        # Added device count
        active_dashboards=active_dashboards
    )

@dashboard_bp.route("/edit/<int:dashboard_id>", methods=["GET", "POST"])
@login_required
def edit_dashboard(dashboard_id):
    dashboard = Dashboard.query.get_or_404(dashboard_id)

    if request.method == "POST":
        # Update dashboard details
        dashboard.name = request.form.get("name")
        dashboard.description = request.form.get("description")
        db.session.commit()
        flash("Dashboard updated successfully!", "success")
        return redirect(url_for("dashboard.dashboard_list"))

    return render_template("dashboard/edit_dashboard.html", dashboard=dashboard)

@dashboard_bp.app_context_processor
def utility_processor():
    
    def get_sensor_icon(sensor_type):

        icon_map = {

            # Environmental Params
            'temperature': 'thermometer-half',
            'temp': 'thermometer-half',
            'humidity': 'tint',
            'rh': 'tint',
            'co2': 'wind',
            'tvoc': 'biohazard',
            'voc': 'biohazard',
            'iaq': 'smog',
            'pm2.5': 'smog',
            'pm25': 'smog',
            'pm10': 'smog',
            'o3': 'cloud',
            'ozone': 'cloud',
            'hcho': 'vial',
            'formaldehyde': 'vial',

            # Pressure / Weather
            'pressure': 'tachometer-alt',
            'barometric': 'tachometer-alt',

            # Light / Lux
            'light': 'lightbulb',
            'lux': 'sun',

            # Motion / People Counting
            'motion': 'running',
            'pir': 'running',
            'people_count': 'users',
            'count': 'users',
            'sound': 'volume-up',
            'noise': 'volume-up',

            # Water Leak (EM300)
            'water': 'water',
            'leak': 'water',
            'water_leak': 'water',

            # Vibration / Tilt / Accelerometer
            'vibration': 'wave-square',
            'tilt': 'mobile-alt',
            'acceleration': 'wave-square',

            # Electrical (WS series)
            'voltage': 'bolt',
            'current': 'bolt',
            'power': 'bolt',
            'energy': 'bolt',

            # Gas Sensors (GS301)
            'gas': 'burn',
            'nh3': 'vial',
            'no2': 'cloud',
            'co': 'cloud',
            'so2': 'cloud',
            'ch4': 'fire',

            # Battery & Signal
            'battery': 'battery-half',
            'rssi': 'signal',
            'snr': 'wave-square',
            'signal': 'signal',

            # Location
            'gps': 'map-marker-alt',
            'latitude': 'map-marker-alt',
            'longitude': 'map-marker-alt',

            # Default icon
            'default': 'chart-line'
        }

        if not sensor_type:
            return icon_map['default']

        key = sensor_type.lower()
        return icon_map.get(key, icon_map['default'])

    def get_sensor_status(sensor):
        return 'success'
    
    return dict(get_sensor_icon=get_sensor_icon, get_sensor_status=get_sensor_status)




@dashboard_bp.route('/view/<int:dashboard_id>')
@login_required
def view_dashboard(dashboard_id):
    """View a specific dashboard with only the devices linked to it"""
    dashboard = Dashboard.query.get_or_404(dashboard_id)

    # Use the same access logic as dashboard_list
    accessible_dashboards = get_accessible_dashboards(current_user)
    accessible_dashboard_ids = [d.id for d in accessible_dashboards]
    
    if dashboard.id not in accessible_dashboard_ids:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.dashboard_list'))


    # DEBUG: First, let's check what's actually in the DashboardSensor table
    # dashboard_sensor_count = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).count()
    # print(f"DEBUG: Found {dashboard_sensor_count} DashboardSensor entries for dashboard {dashboard_id}")

    # Get all dashboard sensor relationships
    dashboard_sensor_relations = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
    for relation in dashboard_sensor_relations:
        print(f"DEBUG: DashboardSensor - ID: {relation.id}, Device ID: {relation.device_id}")

    # Get ONLY the devices that are linked to this dashboard via DashboardSensor
    # CHANGED: Added filter for Device.is_active == True
    dashboard_devices = (
        db.session.query(Device)
        .join(DashboardSensor, DashboardSensor.device_id == Device.id)
        .filter(DashboardSensor.dashboard_id == dashboard_id)
        .filter(Device.is_active == True)  # <-- ADDED THIS FILTER
        .all()
    )
    
    print(f"DEBUG: Query returned {len(dashboard_devices)} devices (active only)")

    # If no devices found, let's check why
    if len(dashboard_devices) == 0:
        print("DEBUG: No active devices found. Checking if active devices exist in database...")
        # Check for active devices in general
        active_devices_count = Device.query.filter_by(is_active=True).count()
        print(f"DEBUG: Total active devices in database: {active_devices_count}")

    devices_dict = {}
    for device in dashboard_devices:
        print(f"DEBUG: Processing device {device.id} - {device.name} (is_active={device.is_active})")
        device_id = device.id
        
        devices_dict[device_id] = {
            'device': device,
            'parameters': {},
            'last_seen': None,
            'last_seen_datetime': None
        }
        
        # Get sensor data for this device - adjust this based on your SensorData model
        try:
            latest_readings = (
                db.session.query(SensorData)
                .filter(SensorData.device_id == device_id)
                .order_by(SensorData.timestamp.desc())
                .all()
            )
            
            print(f"DEBUG: Found {len(latest_readings)} sensor readings for device {device_id}")
            
            for reading in latest_readings:
                # Create a unique key for each parameter type
                param_type = getattr(reading, 'parameter_type', 'unknown')
                param_key = f"{param_type}_{reading.id}"
                
                # Only take the first (latest) reading for each parameter type
                if param_type not in devices_dict[device_id]['parameters']:
                    devices_dict[device_id]['parameters'][param_type] = {
                        'value': reading.value,
                        'unit': getattr(reading, 'unit', ''),
                        'timestamp': to_ist(reading.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                        'parameter_type': param_type,
                        'sensor_name': getattr(reading, 'sensor_name', param_type.replace('_', ' ').title())
                    }
                    
                    # Update last_seen - make sure both datetimes are timezone-aware or both naive
                    reading_timestamp = reading.timestamp
                    current_time = datetime.utcnow()
                    
                    # If reading timestamp is timezone-aware, make current_time aware too
                    if reading_timestamp.tzinfo is not None:
                        from datetime import timezone
                        current_time = current_time.replace(tzinfo=timezone.utc)
                    
                    if not devices_dict[device_id]['last_seen_datetime'] or reading_timestamp > devices_dict[device_id]['last_seen_datetime']:
                        devices_dict[device_id]['last_seen_datetime'] = reading_timestamp
                        devices_dict[device_id]['last_seen'] = to_ist(reading_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        
        except Exception as e:
            print(f"DEBUG: Error getting sensor data for device {device_id}: {e}")

    print(f"DEBUG: devices_dict has {len(devices_dict)} devices with data (all active)")

    # Convert to list for template
    devices_data = []
    active_devices = 0
    
    for device_id, device_info in devices_dict.items():
        # Calculate active status - FIXED datetime comparison
        # Note: This is for "online/offline" status based on last_seen timestamp
        # This is DIFFERENT from the is_active column filter we applied earlier
        if device_info['last_seen_datetime']:
            last_seen = device_info['last_seen_datetime']
            current_time = datetime.utcnow()
            
            # Handle timezone-aware and naive datetime comparison
            if last_seen.tzinfo is not None and current_time.tzinfo is None:
                # Make current_time timezone-aware to match last_seen
                from datetime import timezone
                current_time = current_time.replace(tzinfo=timezone.utc)
            elif last_seen.tzinfo is None and current_time.tzinfo is not None:
                # Make last_seen timezone-aware to match current_time
                from datetime import timezone
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            
            time_diff = (current_time - last_seen).total_seconds()
            device_info['is_active'] = time_diff < 3600  # 1 hour for online/offline status
        else:
            device_info['is_active'] = False
            
        if device_info['is_active']:
            active_devices += 1
        
        device_info.pop('last_seen_datetime', None)
        devices_data.append(device_info)

    # Statistics
    total_devices = len(devices_data)
    total_parameters = sum(len(device['parameters']) for device in devices_data)

    print(f"DEBUG: Final - {total_devices} active devices, {total_parameters} parameters, {active_devices} recently active (online)")

    # Navigation settings (your existing code)
    navigation_settings_obj = NavigationSettings.query.filter_by(dashboard_id=dashboard_id).first()
    
    if navigation_settings_obj:
        navigation_settings = {
            "analytics": navigation_settings_obj.analytics or False,
            "reports": navigation_settings_obj.reports or False,
            "dashboard_management": navigation_settings_obj.dashboard_management or False,
            "settings": navigation_settings_obj.settings or False,
            "download": navigation_settings_obj.download or False,
            "support": navigation_settings_obj.support or False
        }
    else:
        navigation_settings = {
            "analytics": True,
            "reports": True,
            "dashboard_management": True,
            "settings": True,
            "download": True,
            "support": True
        }

    return render_template('dashboard/view_dashboard.html',
                           dashboard=dashboard,
                           devices_data=devices_data,
                           total_devices=total_devices,
                           total_parameters=total_parameters,
                           total_linked_sensors=total_parameters,
                           navigation_settings=navigation_settings,
                           total_readings=total_parameters,
                           active_devices=active_devices)





@dashboard_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_dashboard():
    """Create a new dashboard (admin and super_admin only)"""
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard.dashboard_list'))
    
    if request.method == 'POST':
        try:
            validate_csrf(request.form.get('csrf_token'))
            
            name = request.form.get('name')
            description = request.form.get('description')
            company_id = request.form.get('company_id')
            selected_devices = request.form.getlist('selected_devices')  # Get selected device IDs
            
            if current_user.role == 'admin':
                company_id = current_user.company_id
            
            # Validate required fields
            if not name:
                flash('Dashboard name is required.', 'error')
                return redirect(url_for('dashboard.create_dashboard'))
            
            if not selected_devices:
                flash('Please select at least one device for the dashboard.', 'error')
                return redirect(url_for('dashboard.create_dashboard'))
            
            # Create dashboard
            dashboard = Dashboard(
                name=name,
                description=description,
                company_id=company_id,
                created_by=current_user.id
            )
            
            db.session.add(dashboard)
            db.session.flush()  # Get the dashboard ID without committing
            
            # Add device relationships to dashboard_sensors table
            for device_id in selected_devices:
                # Validate that the device exists and belongs to the same company
                device = Device.query.filter_by(id=device_id).first()
                if device and (current_user.role == 'super_admin' or device.company_id == current_user.company_id):
                    dashboard_sensor = DashboardSensor(
                        dashboard_id=dashboard.id,
                        device_id=device_id
                    )
                    db.session.add(dashboard_sensor)
                else:
                    flash(f'Device ID {device_id} is not accessible or does not exist.', 'warning')
            
            db.session.commit()
            
            flash('Dashboard created successfully with {} devices!'.format(len(selected_devices)), 'success')
            return redirect(url_for('dashboard.view_dashboard', dashboard_id=dashboard.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating dashboard: {str(e)}', 'error')
    
    companies = []
    if current_user.role == 'super_admin':
        companies = Company.query.all()
    
    # Changed: Get accessible parameters (not sensors)
    accessible_parameters = get_accessible_parameters(current_user)
    
    # Get devices for the initial company (if available)
    devices = []
    if current_user.role == 'admin':
        devices = Device.query.filter_by(company_id=current_user.company_id).all()
    elif current_user.role == 'super_admin' and companies:
        # Get devices for the first company by default
        first_company_id = companies[0].id if companies else None
        if first_company_id:
            devices = Device.query.filter_by(company_id=first_company_id).all()
    
    return render_template('dashboard/create_dashboard.html',
                         companies=companies,
                         parameters=accessible_parameters,  
                         devices=devices)

# Add this API endpoint within the dashboard blueprint
@dashboard_bp.route('/api/companies/<int:company_id>/devices')
@login_required
def get_company_devices(company_id):
    """API endpoint to get devices for a specific company"""
    print(f"API called for company_id: {company_id}")
    
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({'error': 'Access denied'}), 403
    
    if current_user.role == 'admin' and company_id != current_user.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        company = Company.query.get(company_id)
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        devices = Device.query.filter_by(company_id=company_id).all()
        print(f"Found {len(devices)} devices for company {company_id}")
        
        devices_data = []
        for device in devices:
            # Get parameters for this device
            parameters = Parameter.query.filter_by(device_id=device.id).all()
            
            device_data = {
                'id': device.id,
                'name': device.name,
                'device_id': device.device_id,  # From your devices table
                'mqtt_topic': device.mqtt_topic,
                'is_active': device.is_active,
                'last_seen': device.last_seen.isoformat() if device.last_seen else None,
                'dev_eui': device.dev_eui,
                'parameters': []
            }
            
            # Add parameter information
            for param in parameters:
                param_data = {
                    'id': param.id,
                    'name': param.name,
                    'sensor_type': param.sensor_type,
                    'unit': param.unit
                }
                device_data['parameters'].append(param_data)
            
            devices_data.append(device_data)
        
        return jsonify(devices_data)
        
    except Exception as e:
        print(f"Error in get_company_devices: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': 'Failed to load devices'}), 500
    


@dashboard_bp.route('/manage/<int:dashboard_id>')
@login_required
def manage_dashboard(dashboard_id):
    """Manage dashboard devices and user assignments"""
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    
    # Check permissions
    if current_user.role == 'user':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard.dashboard_list'))
    
    if current_user.role == 'admin' and dashboard.company_id != current_user.company_id:
        flash('Access denied to manage this dashboard.', 'error')
        return redirect(url_for('dashboard.dashboard_list'))
    
    # Get current devices (CORRECTED - using device_id)
    dashboard_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
    current_device_ids = list({ds.device_id for ds in dashboard_devices})  # use a set to remove duplicates
    total_devices = len(current_device_ids)

    
    # Get available devices (CORRECTED)
    accessible_devices = get_accessible_devices(current_user, dashboard.company_id)
    available_devices = [d for d in accessible_devices if d.id not in current_device_ids]
    
    # Get current devices assigned to this dashboard (CORRECTED)
    current_devices = [d for d in accessible_devices if d.id in current_device_ids]
    
    # Get user assignments - This part is correct
    if current_user.role in ['super_admin', 'admin']:
        if current_user.role == 'super_admin':
            # Super admin can see all users from the dashboard's company
            all_users = User.query.filter_by(company_id=dashboard.company_id).all()
        else:
            # Admin can only see users from their own company
            all_users = User.query.filter_by(company_id=current_user.company_id).all()
        
        # Get assigned users as User objects
        user_assignments = UserDashboard.query.filter_by(dashboard_id=dashboard_id).all()
        assigned_user_ids = [ua.user_id for ua in user_assignments]
        assigned_users = [user for user in all_users if user.id in assigned_user_ids]
        available_users = [user for user in all_users if user.id not in assigned_user_ids]
    else:
        all_users = []
        assigned_users = []
        available_users = []
    
    return render_template('dashboard/manage_dashboard.html',
                         dashboard=dashboard,
                         current_devices=current_devices,  # CORRECTED: Only devices assigned to this dashboard
                         available_devices=available_devices,  # CORRECTED
                         assigned_users=assigned_users,  # List of User objects
                         available_users=available_users,  # List of User objects
                         all_users=all_users,  # All users for reference
                         total_devices=total_devices)  # Added total devices count



# Add individual sensor to dashboard (updated)
@dashboard_bp.route('/add_parameter/<int:dashboard_id>', methods=['POST'])
@login_required
def add_parameter_to_dashboard(dashboard_id):
    try:
        data = request.get_json()
        parameter_id = data.get('parameter_id')
        
        if not parameter_id:
            return jsonify({'success': False, 'error': 'Parameter ID is required'}), 400
        
        # Check if dashboard exists
        dashboard = Dashboard.query.get_or_404(dashboard_id)
        
        # Check if user has access to this dashboard
        if not (dashboard.created_by == current_user.id or 
                UserDashboard.query.filter_by(user_id=current_user.id, dashboard_id=dashboard_id).first()):
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Check if parameter exists and get its device
        parameter = Parameter.query.get_or_404(parameter_id)
        
        # Since your table uses device_id, we need to check if the device is already added
        existing = DashboardSensor.query.filter_by(
            dashboard_id=dashboard_id,
            device_id=parameter.device_id
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Device is already in the dashboard'}), 400
        
        # Create new dashboard-device association
        dashboard_sensor = DashboardSensor(
            dashboard_id=dashboard_id,
            device_id=parameter.device_id
        )
        
        db.session.add(dashboard_sensor)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Parameter "{parameter.name}" added to dashboard',
            'parameter_name': parameter.name,
            'device_name': parameter.device.name
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Remove individual parameter from dashboard (FIXED)
@dashboard_bp.route('/remove_parameter/<int:dashboard_id>', methods=['POST'])
@login_required
def remove_parameter_from_dashboard(dashboard_id):
    try:
        data = request.get_json()
        parameter_id = data.get('parameter_id')
        
        if not parameter_id:
            return jsonify({'success': False, 'error': 'Parameter ID is required'}), 400
        
        # Check if dashboard exists
        dashboard = Dashboard.query.get_or_404(dashboard_id)
        
        # Check if user has access to this dashboard (FIXED)
        if not (dashboard.created_by == current_user.id or 
                UserDashboard.query.filter_by(user_id=current_user.id, dashboard_id=dashboard_id).first()):
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Check if parameter exists
        parameter = Parameter.query.get_or_404(parameter_id)
        
        # Find the dashboard-device association (using device_id)
        association = DashboardSensor.query.filter_by(
            dashboard_id=dashboard_id,
            device_id=parameter.device_id
        ).first()
        
        if not association:
            return jsonify({'success': False, 'error': 'Device is not in the dashboard'}), 400
        
        db.session.delete(association)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Parameter "{parameter.name}" removed from dashboard',
            'parameter_name': parameter.name,
            'device_name': parameter.device.name
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@dashboard_bp.route('/assign_user/<int:dashboard_id>', methods=['POST'])
@login_required
def assign_user_to_dashboard(dashboard_id):
    """Assign user to dashboard"""
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    
    # Check permissions
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({'error': 'Access denied'}), 403
    
    user_id = request.json.get('user_id')
    
    # Check if user is already assigned
    existing = UserDashboard.query.filter_by(
        dashboard_id=dashboard_id, 
        user_id=user_id
    ).first()
    
    if not existing:
        user_dashboard = UserDashboard(
            dashboard_id=dashboard_id,
            user_id=user_id
        )
        db.session.add(user_dashboard)
        db.session.commit()
    
    return jsonify({'success': True})

@dashboard_bp.route('/unassign_user/<int:dashboard_id>', methods=['POST'])
@login_required
def unassign_user_from_dashboard(dashboard_id):
    """Unassign user from dashboard"""
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    
    # Check permissions
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({'error': 'Access denied'}), 403
    
    user_id = request.json.get('user_id')
    
    UserDashboard.query.filter_by(
        dashboard_id=dashboard_id, 
        user_id=user_id
    ).delete()
    
    db.session.commit()
    
    return jsonify({'success': True})

@dashboard_bp.route('/delete/<int:dashboard_id>', methods=['POST'])
@login_required
def delete_dashboard(dashboard_id):
    """Delete a dashboard"""
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    
    # Check permissions
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.dashboard_list'))
    
    if current_user.role == 'admin' and dashboard.company_id != current_user.company_id:
        flash('Access denied to delete this dashboard.', 'error')
        return redirect(url_for('dashboard.dashboard_list'))
    
    try:
        # Remove associated records
        DashboardSensor.query.filter_by(dashboard_id=dashboard_id).delete()
        UserDashboard.query.filter_by(dashboard_id=dashboard_id).delete()
        
        db.session.delete(dashboard)
        db.session.commit()
        flash('Dashboard deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting dashboard: {str(e)}', 'error')
    
    return redirect(url_for('dashboard.dashboard_list'))

def get_latest_sensor_reading(sensor_id):
    """Get the latest reading for a sensor - implement based on your data model"""
    # This is a placeholder - you'll need to implement this based on your sensor data storage
    # Example:
    # return SensorData.query.filter_by(sensor_id=sensor_id).order_by(SensorData.timestamp.desc()).first()
    return {
        'value': 25.5,
        'timestamp': '2024-01-01 10:30:00',
        'unit': '°C'
    }

# Add all sensors from a device to a dashboard
@dashboard_bp.route('/add_device/<int:dashboard_id>', methods=['POST'])
@login_required
def add_device_to_dashboard(dashboard_id):
    try:
        data = request.get_json()
        device_id = data.get('device_id')
        
        if not device_id:
            return jsonify({'success': False, 'error': 'Device ID is required'}), 400
        
        # Check if dashboard exists
        dashboard = Dashboard.query.get_or_404(dashboard_id)
        
        # Check if user has access to this dashboard
        if not (dashboard.created_by == current_user.id or 
                UserDashboard.query.filter_by(user_id=current_user.id, dashboard_id=dashboard_id).first()):
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Check if device exists
        device = Device.query.get_or_404(device_id)
        
        # Check if device is already in dashboard
        existing = DashboardSensor.query.filter_by(
            dashboard_id=dashboard_id,
            device_id=device_id
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Device is already in the dashboard'}), 400
        
        # Create new dashboard-device association
        dashboard_sensor = DashboardSensor(
            dashboard_id=dashboard_id,
            device_id=device_id
        )
        
        db.session.add(dashboard_sensor)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Device "{device.name}" added to dashboard',
            'device_name': device.name,
            'sensor_count': len(device.sensors)  # If you have this relationship
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    

# Remove all sensors from a device from a dashboard
# Remove all sensors from a device from a dashboard (FIXED)
@dashboard_bp.route('/remove_device/<int:dashboard_id>', methods=['POST'])
@login_required
def remove_device_from_dashboard(dashboard_id):
    try:
        data = request.get_json()
        device_id = data.get('device_id')
        
        if not device_id:
            return jsonify({'success': False, 'error': 'Device ID is required'}), 400
        
        # Check if dashboard exists
        dashboard = Dashboard.query.get_or_404(dashboard_id)
        
        # Check if user has access to this dashboard (FIXED)
        if not (dashboard.created_by == current_user.id or 
                UserDashboard.query.filter_by(user_id=current_user.id, dashboard_id=dashboard_id).first()):
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Check if device exists
        device = Device.query.get_or_404(device_id)
        
        # Find the dashboard-device association (FIXED - simpler approach)
        association = DashboardSensor.query.filter_by(
            dashboard_id=dashboard_id,
            device_id=device_id
        ).first()
        
        if not association:
            return jsonify({'success': False, 'error': 'Device is not in the dashboard'}), 400
        
        db.session.delete(association)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Device "{device.name}" removed from dashboard',
            'device_name': device.name
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    

@dashboard_bp.route('/debug_parameter_structure/<int:dashboard_id>')
@login_required
def debug_parameter_structure(dashboard_id):
    """Debug route to check how parameters are structured for a dashboard"""
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    
    # Get dashboard devices (since DashboardSensor links to devices)
    dashboard_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
    device_ids = [ds.device_id for ds in dashboard_devices]
    
    parameter_details = []
    for device_id in device_ids:
        device = Device.query.get(device_id)
        if device:
            # Get all parameters for this device
            device_parameters = Parameter.query.filter_by(device_id=device_id).all()
            
            # Get unique parameter types from parameters
            parameter_types = set()
            for param in device_parameters:
                parameter_types.add(param.sensor_type)
            
            # Or get from sensor data if available
            data_types = db.session.query(SensorData.parameter_type)\
                                  .filter_by(device_id=device_id)\
                                  .distinct()\
                                  .all()
            data_types = [dt[0] for dt in data_types if dt[0]]
            
            # Combine both sources
            all_types = list(parameter_types.union(set(data_types)))
            
            parameter_details.append({
                'device_id': device.id,
                'device_name': device.name,
                'device_identifier': device.device_id,
                'total_parameters': len(device_parameters),
                'parameters': [{
                    'id': p.id,
                    'name': p.name,
                    'type': p.sensor_type,
                    'unit': p.unit
                } for p in device_parameters],
                'parameter_types': all_types,
                'parameter_type_count': len(all_types)
            })
    
    return jsonify({
        'dashboard_id': dashboard_id,
        'dashboard_name': dashboard.name,
        'total_devices': len(parameter_details),
        'devices': parameter_details
    })