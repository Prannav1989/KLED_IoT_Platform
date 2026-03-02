from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import MQTTConfig, db
from werkzeug.security import generate_password_hash
from sqlalchemy.orm import joinedload

# Create a separate blueprint for MQTT configs
mqtt_config_bp = Blueprint('mqtt_config', __name__, url_prefix='/superadmin')

# Helper function to check admin privileges
def requires_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['admin', 'super_admin']:
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('device.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@mqtt_config_bp.route('/mqtt-configs', methods=['GET', 'POST'])
@login_required
@requires_admin
def mqtt_configs():
    if request.method == 'POST':
        try:
            # Process form data
            name = request.form['name']
            broker_url = request.form['broker_url']
            port = int(request.form['port'])
            username = request.form.get('username')
            password = request.form.get('password')
            ssl_enabled = 'ssl_enabled' in request.form
            
            # Create new config
            config = MQTTConfig(
                name=name,
                broker_url=broker_url,
                port=port,
                username=username,
                password_hash=generate_password_hash(password) if password else None,
                ssl_enabled=ssl_enabled,
                user_id=current_user.id
            )
            
            db.session.add(config)
            db.session.commit()
            flash('MQTT configuration saved successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    # Get all configs with owner information
    configs = MQTTConfig.query.options(joinedload(MQTTConfig.owner)).all()
    return render_template('superadmin_dashboard/mqtt_configs.html', configs=configs)

@mqtt_config_bp.route('/mqtt-configs/edit/<int:config_id>', methods=['GET', 'POST'])
@login_required
@requires_admin
def edit_mqtt_config(config_id):
    config = MQTTConfig.query.get_or_404(config_id)
    
    if request.method == 'POST':
        try:
            # Process form data
            config.name = request.form['name']
            config.broker_url = request.form['broker_url']
            config.port = int(request.form['port'])
            config.username = request.form.get('username')
            
            # Handle password (only update if provided)
            password = request.form.get('password')
            if password:
                config.password_hash = generate_password_hash(password)
            
            config.ssl_enabled = 'ssl_enabled' in request.form
            
            db.session.commit()
            flash('MQTT configuration updated successfully!', 'success')
            return redirect(url_for('mqtt_config.mqtt_configs'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating configuration: {str(e)}', 'error')
    
    return render_template('admin/edit_mqtt_config.html', config=config)

@mqtt_config_bp.route('/mqtt-configs/delete/<int:config_id>', methods=['POST'])
@login_required
@requires_admin
def delete_mqtt_config(config_id):
    config = MQTTConfig.query.get_or_404(config_id)
    
    try:
        db.session.delete(config)
        db.session.commit()
        flash('MQTT configuration deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting configuration: {str(e)}', 'error')
    
    return redirect(url_for('mqtt_config.mqtt_configs'))