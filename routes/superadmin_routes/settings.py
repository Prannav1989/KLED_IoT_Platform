from flask import render_template, request, redirect, url_for, flash, jsonify, Blueprint
from models import db, Dashboard, Device, DashboardSensor
from flask_login import login_required, current_user

dashboard_settings_bp = Blueprint('dashboard_settings', __name__)

# Dashboard settings page
@dashboard_settings_bp.route('/dashboard/<int:dashboard_id>/settings')
@login_required
def dashboard_settings(dashboard_id):
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    
    # Access control
    if current_user.role != 'superadmin' and dashboard.created_by != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.dashboard_list'))

    # Get linked devices
    linked_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
    linked_device_ids = [d.device_id for d in linked_devices]

    # Get available devices not yet linked
    available_devices = Device.query.filter(
        ~Device.id.in_(linked_device_ids) if linked_device_ids else True
    ).all()

    navigation_settings = {
        "analytics": True,
        "reports": True,
        "settings": True,
        "download": True,
        "support": True
    }

    return render_template(
        'dashboard/settings.html',
        dashboard=dashboard,
        linked_sensors=linked_devices,        # renamed but kept variable name for template
        available_sensors=available_devices,  # same here for HTML compatibility
        current_user=current_user,
        navigation_settings=navigation_settings
    )


# Update dashboard info
@dashboard_settings_bp.route('/dashboard/<int:dashboard_id>/settings/update', methods=['POST'])
@login_required
def update_dashboard_settings(dashboard_id):
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    if current_user.role != 'superadmin' and dashboard.created_by != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.dashboard_list'))

    try:
        dashboard.name = request.form.get('name', dashboard.name)
        dashboard.description = request.form.get('description', dashboard.description)
        dashboard.refresh_interval = request.form.get('refresh_interval', 30, type=int)
        db.session.commit()
        flash('Dashboard settings updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating settings: {str(e)}', 'error')

    return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))


# Add device to dashboard
@dashboard_settings_bp.route('/dashboard/<int:dashboard_id>/devices/add', methods=['POST'])
@login_required
def add_device_to_dashboard(dashboard_id):
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    if current_user.role != 'superadmin' and dashboard.created_by != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.dashboard_list'))

    device_id = request.form.get('device_id', type=int)
    if not device_id:
        flash('Please select a device', 'error')
        return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))

    try:
        device = Device.query.get(device_id)
        if not device:
            flash('Device not found', 'error')
            return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))

        # Check if already linked
        existing = DashboardSensor.query.filter_by(dashboard_id=dashboard_id, device_id=device_id).first()
        if existing:
            flash('Device already linked', 'warning')
            return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))

        # Link device
        dashboard_device = DashboardSensor(dashboard_id=dashboard_id, device_id=device_id)
        db.session.add(dashboard_device)
        db.session.commit()
        flash('Device added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding device: {str(e)}', 'error')

    return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))


# Remove device from dashboard
@dashboard_settings_bp.route('/dashboard/<int:dashboard_id>/devices/<int:device_id>/remove', methods=['POST'])
@login_required
def remove_device_from_dashboard(dashboard_id, device_id):
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    if current_user.role != 'superadmin' and dashboard.created_by != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.dashboard_list'))

    try:
        dashboard_device = DashboardSensor.query.filter_by(dashboard_id=dashboard_id, device_id=device_id).first_or_404()
        db.session.delete(dashboard_device)
        db.session.commit()
        flash('Device removed successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error removing device: {str(e)}', 'error')

    return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))


# Delete dashboard
@dashboard_settings_bp.route('/dashboard/<int:dashboard_id>/delete', methods=['POST'])
@login_required
def delete_dashboard(dashboard_id):
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    if current_user.role != 'superadmin' and dashboard.created_by != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.dashboard_list'))

    try:
        DashboardSensor.query.filter_by(dashboard_id=dashboard_id).delete()
        db.session.delete(dashboard)
        db.session.commit()
        flash('Dashboard deleted successfully', 'success')
        return redirect(url_for('dashboard.dashboard_list'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting dashboard: {str(e)}', 'error')
        return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))


# API endpoint: get dashboard settings
@dashboard_settings_bp.route('/api/dashboard/<int:dashboard_id>/settings', methods=['GET'])
@login_required
def get_dashboard_settings_api(dashboard_id):
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    if current_user.role != 'superadmin' and dashboard.created_by != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    return jsonify({
        'id': dashboard.id,
        'name': dashboard.name,
        'description': dashboard.description,
        'refresh_interval': dashboard.refresh_interval,
        'created_at': dashboard.created_at.isoformat() if dashboard.created_at else None
    })


# API endpoint: get dashboard devices
@dashboard_settings_bp.route('/api/dashboard/<int:dashboard_id>/devices', methods=['GET'])
@login_required
def get_dashboard_devices_api(dashboard_id):
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    if current_user.role != 'superadmin' and dashboard.created_by != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    linked_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
    devices_data = []
    for ds in linked_devices:
        device = Device.query.get(ds.device_id)
        if device:
            devices_data.append({
                'id': device.id,
                'name': device.name,
                'type': getattr(device, 'type', 'N/A'),
                'last_seen': getattr(device, 'last_seen', None).isoformat() if getattr(device, 'last_seen', None) else None
            })

    return jsonify({'devices': devices_data})
