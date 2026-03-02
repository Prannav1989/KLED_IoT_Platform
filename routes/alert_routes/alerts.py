from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models import (
    AlertRule, AlertEvent, Device, User, SensorModel, 
    db, AlertActionLog, NotificationTemplate, SensorAction, 
    WebNotification, MQTTConfig, Parameter, SensorData, AlertRulePhoneMap,
    PhoneNumber, SmsTemplate
)
import json
from flask_socketio import join_room, leave_room
import asyncio
import threading
from sqlalchemy import desc, func, and_, or_
from extensions import socketio


alerts_bp = Blueprint("alerts", __name__, url_prefix="/alerts")

@alerts_bp.route("/rules")
@login_required
def rules():
    """Display all alert rules with filtering and pagination"""

    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    per_page = 20

    # =========================================================
    # Base query & filters
    # =========================================================
    query = AlertRule.query

    if status_filter == 'enabled':
        query = query.filter(AlertRule.enabled.is_(True))
    elif status_filter == 'disabled':
        query = query.filter(AlertRule.enabled.is_(False))
    elif status_filter == 'recent':
        yesterday = datetime.utcnow() - timedelta(hours=24)
        query = query.filter(AlertRule.last_triggered >= yesterday)

    # Apply company filter for non-super admins
    if current_user.role != "super_admin":
        query = query.filter(AlertRule.company_id == current_user.company_id)

    # =========================================================
    # Stats
    # =========================================================
    # Base stats query with company filter
    if current_user.role == "super_admin":
        total_rules = AlertRule.query.count()
        active_rules = AlertRule.query.filter_by(enabled=True).count()
        total_devices = Device.query.count()
        devices_with_rules = db.session.query(AlertRule.device_id).distinct().count()
    else:
        total_rules = AlertRule.query.filter_by(company_id=current_user.company_id).count()
        active_rules = AlertRule.query.filter_by(company_id=current_user.company_id, enabled=True).count()
        total_devices = Device.query.filter_by(company_id=current_user.company_id).count()
        devices_with_rules = db.session.query(AlertRule.device_id)\
            .filter(AlertRule.company_id == current_user.company_id)\
            .distinct().count()

    device_coverage = int((devices_with_rules / total_devices * 100)) if total_devices else 0

    yesterday = datetime.utcnow() - timedelta(hours=24)
    
    # Events stats with company filter
    if current_user.role == "super_admin":
        triggers_24h = AlertEvent.query.filter(
            AlertEvent.triggered_at >= yesterday
        ).count()
    else:
        triggers_24h = AlertEvent.query\
            .join(AlertRule)\
            .filter(
                AlertEvent.triggered_at >= yesterday,
                AlertRule.company_id == current_user.company_id
            ).count()

    # Action stats with company filter
    if current_user.role == "super_admin":
        total_actions = AlertActionLog.query.filter(
            AlertActionLog.executed_at >= yesterday
        ).count()
        successful_actions = AlertActionLog.query.filter(
            AlertActionLog.executed_at >= yesterday,
            AlertActionLog.status == 'sent'
        ).count()
    else:
        total_actions = AlertActionLog.query\
            .join(AlertRule)\
            .filter(
                AlertActionLog.executed_at >= yesterday,
                AlertRule.company_id == current_user.company_id
            ).count()
        successful_actions = AlertActionLog.query\
            .join(AlertRule)\
            .filter(
                AlertActionLog.executed_at >= yesterday,
                AlertActionLog.status == 'sent',
                AlertRule.company_id == current_user.company_id
            ).count()

    success_rate = int((successful_actions / total_actions * 100)) if total_actions else 100

    # =========================================================
    # Pagination
    # =========================================================
    pagination = query.order_by(AlertRule.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    # =========================================================
    # Enrich rules
    # =========================================================
    enriched_rules = []
    for rule in pagination.items:
        device = Device.query.get(rule.device_id)
        parameter = Parameter.query.get(rule.parameter_id) if rule.parameter_id else None
        
        # Get trigger count for this rule
        trigger_count = AlertEvent.query.filter_by(rule_id=rule.id).count()
        
        # Get last triggered time (safely)
        last_triggered = None
        if hasattr(rule, 'last_triggered'):
            last_triggered = rule.last_triggered
        
        # Get phone numbers for SMS actions
        phone_mappings = AlertRulePhoneMap.query.filter_by(rule_id=rule.id).all()
        phone_numbers = []
        for mapping in phone_mappings:
            phone = PhoneNumber.query.get(mapping.phone_number_id)
            if phone:
                phone_numbers.append({
                    'id': phone.id,
                    'phone_number': phone.phone_number,
                    'recipient_name': phone.recipient_name
                })
        
        # Build rule dictionary
        rule_dict = {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description or "",
            "device_id": rule.device_id,
            "device_name": device.name if device else "Unknown Device",
            "device_id_str": str(device.id) if device else "N/A",
            "parameter_id": rule.parameter_id,
            "metric": rule.metric,
            "parameter_type": rule.parameter_type,
            "unit": rule.unit or (parameter.unit if parameter else ""),
            "operator": rule.operator,
            "threshold": rule.threshold,
            "cooldown_seconds": rule.cooldown_seconds,
            "action": json.loads(rule.action) if rule.action else {},
            "action_types": json.loads(rule.action_types) if rule.action_types else [],
            "enabled": rule.enabled,
            "severity": rule.severity,
            "tags": rule.tags or "",
            "trigger_count": trigger_count,
            "phone_numbers": phone_numbers,  # Add phone numbers for this rule
            "last_triggered": last_triggered.isoformat() if last_triggered else None,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
        }
        
        enriched_rules.append(rule_dict)

    # =========================================================
    # Serialize devices for JS
    # =========================================================
    devices_query = Device.query.filter_by(is_active=True)
    if current_user.role != "super_admin":
        devices_query = devices_query.filter_by(company_id=current_user.company_id)
    
    devices_data = []
    for device in devices_query.all():
        devices_data.append({
            "id": device.id,
            "name": device.name,
            "company_id": device.company_id,
            "parameters": [
                {
                    "id": p.id,
                    "name": p.name,
                    "unit": p.unit
                }
                for p in device.parameters.all()
            ]
        })

    # =========================================================
    # Fetch phone numbers for SMS configuration
    # =========================================================
    from sqlalchemy import text
    
    if current_user.role == "super_admin":
        # Super admin sees all phone numbers with company info
        phone_numbers = db.session.execute(text("""
            SELECT 
                p.id, 
                p.phone_number, 
                p.recipient_name,
                p.is_active,
                p.created_at,
                c.name as company_name,
                c.id as company_id
            FROM phone_numbers p
            JOIN companies c ON p.company_id = c.id
            WHERE p.is_active = true
            ORDER BY c.name, p.recipient_name
        """)).fetchall()
        
        # Convert to list of dicts for easier template access
        phone_numbers_list = []
        for phone in phone_numbers:
            phone_numbers_list.append({
                "id": phone.id,
                "phone_number": phone.phone_number,
                "recipient_name": phone.recipient_name,
                "is_active": phone.is_active,
                "company_name": phone.company_name,
                "company_id": phone.company_id
            })
        phone_numbers = phone_numbers_list
        
    else:
        # Regular users see only their company's phone numbers
        phone_numbers = db.session.execute(text("""
            SELECT 
                p.id, 
                p.phone_number, 
                p.recipient_name,
                p.is_active,
                p.created_at
            FROM phone_numbers p
            WHERE p.company_id = :company_id
            AND p.is_active = true
            ORDER BY p.recipient_name
        """), {
            "company_id": current_user.company_id
        }).fetchall()
        
        # Convert to list of dicts
        phone_numbers_list = []
        for phone in phone_numbers:
            phone_numbers_list.append({
                "id": phone.id,
                "phone_number": phone.phone_number,
                "recipient_name": phone.recipient_name,
                "is_active": phone.is_active,
                "company_id": current_user.company_id,
            })
        phone_numbers = phone_numbers_list

    # =========================================================
    # Get users for email notifications (filter by company)
    # =========================================================
    if current_user.role == "super_admin":
        users = User.query.filter_by(active_status=True).all()
    else:
        users = User.query.filter_by(
            company_id=current_user.company_id,
            active_status=True
        ).all()

    # =========================================================
    # Render
    # =========================================================
    return render_template(
        "alerts/rules.html",
        rules=enriched_rules,
        pagination=pagination,
        stats={
            "active_rules": active_rules,
            "triggers_24h": triggers_24h,
            "device_coverage": device_coverage,
            "success_rate": success_rate,
            "total_rules": total_rules
        },
        devices_data=devices_data,
        users=users,
        phone_numbers=phone_numbers,
        current_user=current_user
    )

@alerts_bp.route("/create_rule", methods=["GET", "POST"])
@login_required
def create_rule():
    """Create a new alert rule"""

    # ==========================================
    # GET → Show Create Rule Page
    # ==========================================
    if request.method == "GET":
        # -----------------------------
        # Build devices data properly
        # -----------------------------
        devices_query = Device.query.filter_by(
            company_id=current_user.company_id,
            is_active=True
        )

        devices_data = []
        for device in devices_query.all():
            devices_data.append({
                "id": device.id,
                "name": device.name,
                "parameters": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "unit": p.unit
                    }
                    for p in device.parameters.all()
                ]
            })

        return render_template(
            "alerts/create_alert_rule.html",
            devices_data=devices_data,
            users=User.query.filter_by(
                company_id=current_user.company_id,
                active_status=True
            ).all(),
            phone_numbers=PhoneNumber.query.filter_by(
                company_id=current_user.company_id,
                is_active=True
            ).all(),
            sms_templates=SmsTemplate.query.filter_by(
                company_id=current_user.company_id,
                is_active=True
            ).all()
        )
    
    # ==========================================
    # POST → Handle Form Submission
    # ==========================================
    try:
        print("FORM DATA:", dict(request.form))

        # ---------------------------
        # Required fields
        # ---------------------------
        name = request.form.get("name")
        description = request.form.get("description", "")
        device_id = request.form.get("device_id", type=int)
        parameter_id = request.form.get("parameter_id", type=int)
        operator = request.form.get("operator")
        threshold = request.form.get("threshold", type=float)
        cooldown_seconds = request.form.get(
            "cooldown_seconds", type=int, default=300
        )

        if not name or not device_id or not parameter_id or not operator or threshold is None:
            flash("Missing required fields", "error")
            return redirect(url_for("alerts.create_rule"))

        # ---------------------------
        # Validate parameter
        # ---------------------------
        parameter = Parameter.query.get(parameter_id)
        if not parameter:
            flash("Invalid parameter selected", "error")
            return redirect(url_for("alerts.create_rule"))

        # Validate device belongs to user's company
        device = Device.query.get(device_id)
        if not device or device.company_id != current_user.company_id:
            flash("Invalid device selected", "error")
            return redirect(url_for("alerts.create_rule"))

        # ---------------------------
        # Actions
        # ---------------------------
        actions = request.form.getlist("actions[]")
        action_config = {}
        phone_ids = []

        # EMAIL
        if "email" in actions:
            email_recipients = request.form.getlist("email_recipients[]")
            # Validate email recipients belong to company
            valid_recipients = []
            for recipient_id in email_recipients:
                if recipient_id.isdigit():
                    user = User.query.get(int(recipient_id))
                    if user and user.company_id == current_user.company_id:
                        valid_recipients.append(int(recipient_id))
            
            action_config["email"] = {
                "recipients": valid_recipients,
                "template": request.form.get("email_template", "default")
            }

        # SMS
        if "sms" in actions:
            phone_ids = request.form.getlist("sms_phone_ids[]")
            phone_ids = [int(pid) for pid in phone_ids if pid.isdigit()]
            
            # Validate phone numbers belong to company
            valid_phones = PhoneNumber.query.filter(
                PhoneNumber.id.in_(phone_ids),
                PhoneNumber.company_id == current_user.company_id,
                PhoneNumber.is_active == True
            ).all()
            
            valid_phone_ids = [p.id for p in valid_phones]
            
            if valid_phone_ids:
                action_config["sms"] = {
                    "phone_ids": valid_phone_ids,
                    "template": request.form.get("sms_template", "default")
                }
            else:
                # Remove SMS from actions if no valid phones
                actions.remove("sms")

        # WEB
        if "web" in actions:
            action_config["web"] = {
                "sound": request.form.get("web_sound", "default")
            }

        # AUDIO
        if "audio" in actions:
            action_config["audio"] = {
                "type": request.form.get("audio_type", "beep"),
                "duration": request.form.get(
                    "audio_duration", type=int, default=10
                )
            }

        # LORAWAN
        if "lorawan" in actions:
            action_config["lorawan"] = {
                "command": request.form.get("lorawan_command", "reset"),
                "payload": request.form.get("lorawan_payload", "")
            }

        # ---------------------------
        # Create rule object
        # ---------------------------
        rule = AlertRule(
            name=name,
            description=description,
            device_id=device_id,
            parameter_id=parameter.id,
            metric=parameter.name,
            parameter_type=parameter.sensor_type,
            unit=parameter.unit,
            operator=operator,
            threshold=threshold,
            cooldown_seconds=cooldown_seconds,
            action=json.dumps(action_config),
            action_types=json.dumps(actions),
            enabled=("enabled" in request.form),
            severity=request.form.get("severity", "warning"),
            tags=request.form.get("tags", ""),
            last_triggered=None,
            created_by=current_user.id,
            company_id=current_user.company_id,
            created_at=datetime.utcnow()
        )

        db.session.add(rule)
        db.session.flush()  # Get rule.id without committing

        # ---------------------------
        # Insert phone mappings
        # ---------------------------
        if "sms" in actions and phone_ids:
            for pid in phone_ids:
                # Double-check phone exists and belongs to company
                phone = PhoneNumber.query.filter_by(
                    id=pid, 
                    company_id=current_user.company_id,
                    is_active=True
                ).first()
                if phone:
                    mapping = AlertRulePhoneMap(
                        rule_id=rule.id,
                        phone_number_id=pid
                    )
                    db.session.add(mapping)

        db.session.commit()

        # ---------------------------
        # Start monitoring if enabled
        # ---------------------------
        if rule.enabled:
            start_rule_monitoring(rule.id)

        flash("Alert rule created successfully!", "success")
        return redirect(url_for("alerts.rules"))

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error creating rule")
        flash(f"Error creating rule: {str(e)}", "error")
        return redirect(url_for("alerts.create_rule"))

@alerts_bp.route("/api/get_rule/<int:rule_id>", methods=["GET"])
@login_required
def get_rule_api(rule_id):
    """Edit an existing alert rule"""
    rule = AlertRule.query.get_or_404(rule_id)
    
    # Check permission
    if current_user.role != "super_admin" and rule.company_id != current_user.company_id:
        flash("You don't have permission to edit this rule", "error")
        return redirect(url_for("alerts.rules"))
    
    if request.method == 'GET':
        # Build response with all rule data
        rule_dict = {
            'id': rule.id,
            'name': rule.name,
            'description': rule.description,
            'device_id': rule.device_id,
            'parameter_id': rule.parameter_id,
            'operator': rule.operator,
            'threshold': rule.threshold,
            'cooldown_seconds': rule.cooldown_seconds,
            'enabled': rule.enabled,
            'severity': rule.severity,
            'tags': rule.tags,
        }
        
        # Add actions
        if rule.action:
            rule_dict['action'] = json.loads(rule.action)
        if rule.action_types:
            rule_dict['action_types'] = json.loads(rule.action_types)
        
        # Add phone mappings
        phone_mappings = AlertRulePhoneMap.query.filter_by(rule_id=rule.id).all()
        rule_dict['phone_number_ids'] = [m.phone_number_id for m in phone_mappings]
        
        return jsonify(rule_dict)
    
    # Handle POST request
    try:
        # Update rule fields
        rule.name = request.form.get('name', rule.name)
        rule.description = request.form.get('description', rule.description)
        rule.operator = request.form.get('operator', rule.operator)
        rule.threshold = float(request.form.get('threshold', rule.threshold))
        rule.cooldown_seconds = int(request.form.get('cooldown_seconds', rule.cooldown_seconds))
        rule.severity = request.form.get('severity', rule.severity)
        rule.tags = request.form.get('tags', rule.tags)
        rule.enabled = 'enabled' in request.form
        
        # Update actions
        actions = request.form.getlist('actions[]')
        action_config = {}
        phone_ids = []
        
        if 'email' in actions:
            email_recipients = request.form.getlist('email_recipients[]')
            valid_recipients = []
            for recipient_id in email_recipients:
                if recipient_id.isdigit():
                    user = User.query.get(int(recipient_id))
                    if user and user.company_id == current_user.company_id:
                        valid_recipients.append(int(recipient_id))
            
            action_config['email'] = {
                'recipients': valid_recipients,
                'template': request.form.get('email_template', 'default')
            }
        
        if 'sms' in actions:
            phone_ids = request.form.getlist('sms_phone_ids[]')
            phone_ids = [int(pid) for pid in phone_ids if pid.isdigit()]
            
            # Validate phone numbers
            valid_phones = PhoneNumber.query.filter(
                PhoneNumber.id.in_(phone_ids),
                PhoneNumber.company_id == current_user.company_id,
                PhoneNumber.is_active == True
            ).all()
            
            valid_phone_ids = [p.id for p in valid_phones]
            
            if valid_phone_ids:
                action_config['sms'] = {
                    'phone_ids': valid_phone_ids,
                    'template': request.form.get('sms_template', 'default')
                }
            else:
                # Remove SMS from actions if no valid phones
                actions.remove('sms')
        
        if 'web' in actions:
            action_config['web'] = {
                'sound': request.form.get('web_sound', 'default')
            }
        
        if 'audio' in actions:
            action_config['audio'] = {
                'type': request.form.get('audio_type', 'beep'),
                'duration': int(request.form.get('audio_duration', 10))
            }
        
        if 'lorawan' in actions:
            action_config['lorawan'] = {
                'command': request.form.get('lorawan_command', 'reset'),
                'payload': request.form.get('lorawan_payload', '')
            }
        
        rule.action = json.dumps(action_config)
        rule.action_types = json.dumps(actions)
        rule.updated_at = datetime.utcnow()
        
        # Update phone mappings
        if 'sms' in actions and phone_ids:
            # Delete old mappings
            AlertRulePhoneMap.query.filter_by(rule_id=rule.id).delete()
            # Add new mappings
            for pid in phone_ids:
                phone = PhoneNumber.query.filter_by(
                    id=pid, 
                    company_id=current_user.company_id,
                    is_active=True
                ).first()
                if phone:
                    mapping = AlertRulePhoneMap(
                        rule_id=rule.id,
                        phone_number_id=pid
                    )
                    db.session.add(mapping)
        else:
            # No SMS action, delete all mappings
            AlertRulePhoneMap.query.filter_by(rule_id=rule.id).delete()
        
        db.session.commit()
        
        # Restart monitoring if enabled
        if rule.enabled:
            start_rule_monitoring(rule.id)
        else:
            stop_rule_monitoring(rule.id)
        
        flash('Rule updated successfully!', 'success')
        return redirect(url_for('alerts.rules'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating rule: {str(e)}")
        flash(f'Error updating rule: {str(e)}', 'error')
        return redirect(url_for('alerts.rules'))

@alerts_bp.route("/toggle_rule", methods=["POST"])
@login_required
def toggle_rule():
    """Toggle rule enabled/disabled status"""
    try:
        data = request.get_json()
        rule_id = data.get('rule_id')
        enabled = data.get('enabled')
        
        rule = AlertRule.query.get(rule_id)
        if not rule:
            return jsonify({'success': False, 'message': 'Rule not found'}), 404
        
        # Check permission
        if current_user.role != "super_admin" and rule.company_id != current_user.company_id:
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        
        rule.enabled = enabled
        rule.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Start or stop monitoring
        if enabled:
            start_rule_monitoring(rule.id)
        else:
            stop_rule_monitoring(rule.id)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling rule: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@alerts_bp.route("/test_rule/<int:rule_id>")
@login_required
def test_rule(rule_id):
    """Test a rule with current conditions"""
    try:
        rule = AlertRule.query.get_or_404(rule_id)
        
        # Check permission
        if current_user.role != "super_admin" and rule.company_id != current_user.company_id:
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        
        # Get latest sensor data for this device and parameter
        latest_data = SensorData.query.filter_by(
            device_id=rule.device_id,
            parameter_type=rule.metric
        ).order_by(SensorData.timestamp.desc()).first()
        
        if not latest_data:
            return jsonify({
                'success': False,
                'message': 'No recent data available for testing'
            })
        
        # Evaluate the rule
        from rule_engine.engine import compare
        should_trigger = compare(
            float(latest_data.value),
            rule.operator,
            float(rule.threshold)
        )
        
        if should_trigger:
            # Get actions that would be triggered
            actions = json.loads(rule.action_types) if rule.action_types else []
            return jsonify({
                'success': True,
                'should_trigger': True,
                'current_value': latest_data.value,
                'threshold': rule.threshold,
                'actions': actions
            })
        else:
            return jsonify({
                'success': True,
                'should_trigger': False,
                'current_value': latest_data.value,
                'threshold': rule.threshold,
                'message': f'Current value {latest_data.value} does not meet condition {rule.operator} {rule.threshold}'
            })
            
    except Exception as e:
        current_app.logger.error(f"Error testing rule: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@alerts_bp.route("/delete_rule/<int:rule_id>", methods=["DELETE"])
@login_required
def delete_rule(rule_id):
    """Delete an alert rule"""
    try:
        rule = AlertRule.query.get_or_404(rule_id)
        
        # Check permission
        if current_user.role != "super_admin" and rule.company_id != current_user.company_id:
            return jsonify({'success': False, 'message': 'Permission denied'}), 403

        # Stop monitoring if active
        if rule.enabled:
            stop_rule_monitoring(rule.id)

        # Delete phone mappings first
        AlertRulePhoneMap.query.filter_by(rule_id=rule_id).delete()

        # Delete action logs linked to alert events
        event_ids = db.session.query(AlertEvent.id).filter(AlertEvent.rule_id == rule_id).subquery()
        AlertActionLog.query.filter(AlertActionLog.alert_event_id.in_(event_ids)).delete(synchronize_session=False)

        # Delete alert events
        AlertEvent.query.filter_by(rule_id=rule_id).delete()

        # Delete the rule itself
        db.session.delete(rule)
        db.session.commit()

        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error deleting rule")
        return jsonify({"success": False, "message": str(e)}), 500

@alerts_bp.route("/events")
@login_required
def events():
    """Display alert events (triggers)"""

    page = request.args.get("page", 1, type=int)
    per_page = 50
    rule_id = request.args.get("rule_id", type=int)
    device_id = request.args.get("device_id", type=int)

    query = AlertEvent.query

    # Apply company filter
    if current_user.role != "super_admin":
        query = query.join(AlertRule).filter(AlertRule.company_id == current_user.company_id)

    # Apply additional filters
    if rule_id:
        query = query.filter(AlertEvent.rule_id == rule_id)

    if device_id:
        query = query.filter(AlertEvent.device_id == device_id)

    # Paginate results
    pagination = query.order_by(AlertEvent.triggered_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    events = pagination.items

    # Load rules and devices once
    if current_user.role == "super_admin":
        rules_map = {r.id: r for r in AlertRule.query.all()}
        devices_map = {d.id: d for d in Device.query.all()}
    else:
        rules_map = {r.id: r for r in AlertRule.query.filter_by(company_id=current_user.company_id).all()}
        devices_map = {d.id: d for d in Device.query.filter_by(company_id=current_user.company_id).all()}

    enriched_events = []

    for event in events:
        enriched_events.append({
            "id": event.id,
            "rule_id": event.rule_id,
            "device_id": event.device_id,
            "parameter_type": event.parameter_type,
            "actual_value": event.actual_value,
            "threshold": event.threshold,
            "triggered_at": event.triggered_at.strftime("%Y-%m-%d %H:%M:%S")
            if event.triggered_at else None,
            "status": event.status,
            "source": event.source,
            "rule_name": rules_map[event.rule_id].name
            if event.rule_id in rules_map else "Unknown Rule",
            "device_name": devices_map[event.device_id].name
            if event.device_id in devices_map else "Unknown Device"
        })

    return render_template(
        "alerts/events.html",
        events=enriched_events,
        pagination=pagination,
        rules=list(rules_map.values()),
        devices=list(devices_map.values())
    )

@alerts_bp.route("/logs")
@login_required
def logs():
    """Display action logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    rule_id = request.args.get('rule_id')
    action_type = request.args.get('action_type')
    status = request.args.get('status')
    
    query = AlertActionLog.query
    
    # Apply company filter
    if current_user.role != "super_admin":
        query = query.join(AlertRule).filter(AlertRule.company_id == current_user.company_id)
    
    # Apply additional filters
    if rule_id and rule_id.isdigit():
        query = query.filter_by(rule_id=int(rule_id))
    if action_type:
        query = query.filter_by(action_type=action_type)
    if status:
        query = query.filter_by(status=status)
    
    # Paginate results
    pagination = query.order_by(AlertActionLog.executed_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    logs = pagination.items
    
    # Enrich logs data
    enriched_logs = []
    for log in logs:
        log_dict = {
            'id': log.id,
            'alert_event_id': log.alert_event_id,
            'action_type': log.action_type,
            'target': json.loads(log.target) if log.target else None,
            'payload': json.loads(log.payload) if log.payload else None,
            'status': log.status,
            'error_message': log.error_message,
            'executed_at': log.executed_at.strftime("%Y-%m-%d %H:%M:%S") if log.executed_at else None
        }
        rule = AlertRule.query.get(log.rule_id)
        device = Device.query.get(log.device_id)
        log_dict['rule_name'] = rule.name if rule else 'Unknown Rule'
        log_dict['device_name'] = device.name if device else 'Unknown Device'
        enriched_logs.append(log_dict)
    
    # Get rules for filter dropdown
    if current_user.role == "super_admin":
        rules = AlertRule.query.all()
    else:
        rules = AlertRule.query.filter_by(company_id=current_user.company_id).all()
    
    return render_template(
        "alerts/logs.html",
        logs=enriched_logs,
        pagination=pagination,
        rules=rules
    )

@alerts_bp.route("/notifications")
@login_required
def notifications():
    """Display web notifications for current user"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = WebNotification.query.filter_by(user_id=current_user.id)
    
    # Mark as read when viewing
    WebNotification.query.filter_by(
        user_id=current_user.id, 
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    
    # Paginate results
    pagination = query.order_by(WebNotification.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    notifications = pagination.items
    
    return render_template(
        "alerts/notifications.html",
        notifications=notifications,
        pagination=pagination
    )

@alerts_bp.route("/clear_notifications", methods=["POST"])
@login_required
def clear_notifications():
    """Clear all notifications for current user"""
    try:
        WebNotification.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing notifications: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@alerts_bp.route("/dashboard_stats")
@login_required
def dashboard_stats():
    """Get dashboard statistics for alerts"""
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    last_week = now - timedelta(days=7)
    
    # Apply company filter
    if current_user.role == "super_admin":
        stats = {
            'total_rules': AlertRule.query.count(),
            'active_rules': AlertRule.query.filter_by(enabled=True).count(),
            'today_triggers': AlertEvent.query.filter(
                AlertEvent.triggered_at >= yesterday
            ).count(),
            'week_triggers': AlertEvent.query.filter(
                AlertEvent.triggered_at >= last_week
            ).count(),
            'success_rate': calculate_success_rate(),
            'recent_alerts': get_recent_alerts(5)
        }
    else:
        stats = {
            'total_rules': AlertRule.query.filter_by(company_id=current_user.company_id).count(),
            'active_rules': AlertRule.query.filter_by(company_id=current_user.company_id, enabled=True).count(),
            'today_triggers': AlertEvent.query.join(AlertRule).filter(
                AlertEvent.triggered_at >= yesterday,
                AlertRule.company_id == current_user.company_id
            ).count(),
            'week_triggers': AlertEvent.query.join(AlertRule).filter(
                AlertEvent.triggered_at >= last_week,
                AlertRule.company_id == current_user.company_id
            ).count(),
            'success_rate': calculate_success_rate(),
            'recent_alerts': get_recent_alerts(5)
        }
    
    return jsonify(stats)

@alerts_bp.route("/trigger_rule", methods=["POST"])
@login_required
def trigger_rule():
    """Manually trigger a rule (for testing)"""
    try:
        data = request.get_json() or {}
        rule_id = data.get("rule_id")
        test_value = data.get("test_value")

        if rule_id is None or test_value is None:
            return jsonify({
                "success": False,
                "message": "rule_id and test_value are required"
            }), 400

        # Load rule
        rule = AlertRule.query.get_or_404(rule_id)
        
        # Check permission
        if current_user.role != "super_admin" and rule.company_id != current_user.company_id:
            return jsonify({'success': False, 'message': 'Permission denied'}), 403

        # Import rule engine
        from rule_engine.engine import compare

        # Check condition manually
        condition_met = compare(
            float(test_value),
            rule.operator,
            float(rule.threshold)
        )

        if condition_met:
            # Create alert event
            alert_event = create_alert_event(
                rule=rule,
                device_id=rule.device_id,
                parameter_type=rule.parameter_type,
                actual_value=float(test_value),
                threshold=float(rule.threshold),
                source='manual'
            )

        return jsonify({
            "success": True,
            "triggered": condition_met,
            "rule": rule.name,
            "operator": rule.operator,
            "threshold": rule.threshold,
            "test_value": test_value,
            "alert_event_id": alert_event.id if condition_met and alert_event else None
        })

    except Exception as e:
        current_app.logger.exception("Error triggering rule manually")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# ==========================================
# Helper Functions
# ==========================================

def create_alert_event(rule, device_id, parameter_type, actual_value, threshold, source='auto'):
    """
    Create an entry in alert_event table when a rule is triggered
    
    Args:
        rule: AlertRule object
        device_id: Device ID
        parameter_type: Parameter type (e.g., 'temperature')
        actual_value: The actual sensor value
        threshold: The threshold value from rule
        source: 'auto' (sensor trigger) or 'manual' (user test)
    """
    try:
        # Check if event should be created (respect cooldown)
        if rule.last_triggered:
            time_since_last = datetime.utcnow() - rule.last_triggered
            if time_since_last.total_seconds() < rule.cooldown_seconds:
                current_app.logger.info(f"Rule {rule.id} in cooldown. Skipping event creation.")
                return None
        
        # Create the alert event
        alert_event = AlertEvent(
            rule_id=rule.id,
            device_id=device_id,
            parameter_type=parameter_type,
            actual_value=actual_value,
            threshold=threshold,
            triggered_at=datetime.utcnow(),
            status='active',
            source=source
        )
        
        db.session.add(alert_event)
        db.session.flush()  # Get alert_event.id
        
        # Update rule's last_triggered timestamp
        rule.last_triggered = datetime.utcnow()
        db.session.commit()
        
        current_app.logger.info(f"Alert event created for rule {rule.id}: {parameter_type} = {actual_value}")
        
        # Trigger actions based on rule configuration
        trigger_alert_actions(rule, alert_event, actual_value)
        
        return alert_event
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating alert event: {str(e)}")
        return None

def trigger_alert_actions(rule, alert_event, actual_value):
    """
    Execute actions configured for the rule (email, sms, web, audio, etc.)
    """
    try:
        if not rule.action:
            return
        
        actions_config = json.loads(rule.action) if rule.action else {}
        action_types = json.loads(rule.action_types) if rule.action_types else []
        
        # 1. Web Notification (Always create for dashboard)
        notification = WebNotification(
            user_id=rule.created_by,
            title=f"Alert: {rule.name}",
            message=f"{rule.parameter_type} = {actual_value} {rule.unit} ({rule.operator} {rule.threshold})",
            notification_type='alert',
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
        
        # 2. Email Action
        if 'email' in action_types and 'email' in actions_config:
            config = actions_config['email']
            recipients = config.get('recipients', [])
            if recipients:
                # Get user emails
                users = User.query.filter(User.id.in_(recipients)).all()
                email_addresses = [u.email for u in users if u.email]
                # TODO: Implement actual email sending
                log_action('email', rule, alert_event, email_addresses, 'sent')
        
        # 3. SMS Action
        if 'sms' in action_types and 'sms' in actions_config:
            config = actions_config['sms']
            phone_ids = config.get('phone_ids', [])
            if phone_ids:
                # Get phone numbers
                phones = PhoneNumber.query.filter(
                    PhoneNumber.id.in_(phone_ids),
                    PhoneNumber.is_active == True
                ).all()
                phone_numbers = [p.phone_number for p in phones]
                # TODO: Implement actual SMS sending via SMS gateway
                log_action('sms', rule, alert_event, phone_numbers, 'sent')
        
        # 4. Audio Action
        if 'audio' in action_types and 'audio' in actions_config:
            config = actions_config['audio']
            # TODO: Implement audio alert in frontend
            log_action('audio', rule, alert_event, config, 'sent')
        
        # 5. LoRaWAN Action
        if 'lorawan' in action_types and 'lorawan' in actions_config:
            config = actions_config['lorawan']
            # TODO: Implement LoRaWAN downlink
            log_action('lorawan', rule, alert_event, config, 'sent')
        
        db.session.commit()
        
        # Emit SocketIO event for real-time updates
        socketio.emit('new_alert', {
            'rule_id': rule.id,
            'rule_name': rule.name,
            'device_id': rule.device_id,
            'parameter': rule.parameter_type,
            'value': actual_value,
            'threshold': rule.threshold,
            'severity': rule.severity,
            'timestamp': datetime.utcnow().isoformat()
        }, room=f"alerts_user_{rule.created_by}")
        
        # Also emit to company room for broadcast if needed
        socketio.emit('company_alert', {
            'rule_name': rule.name,
            'device_id': rule.device_id,
            'message': f"{rule.parameter_type} = {actual_value} {rule.unit}"
        }, room=f"company_{rule.company_id}")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error triggering alert actions: {str(e)}")

def log_action(action_type, rule, alert_event, target, status='sent', error_message=None):
    """
    Log an action to alert_action_log table
    """
    try:
        action_log = AlertActionLog(
            alert_event_id=alert_event.id,
            rule_id=rule.id,
            device_id=rule.device_id,
            action_type=action_type,
            target=json.dumps(target) if target else None,
            payload=json.dumps({
                'rule_id': rule.id,
                'device_id': rule.device_id,
                'parameter': rule.parameter_type,
                'value': alert_event.actual_value,
                'threshold': rule.threshold,
                'unit': rule.unit
            }),
            status=status,
            error_message=error_message,
            executed_at=datetime.utcnow()
        )
        db.session.add(action_log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error logging action: {str(e)}")

def start_rule_monitoring(rule_id):
    """
    No-op for now - rules are evaluated dynamically when sensor data arrives.
    """
    current_app.logger.info(f"Rule {rule_id} enabled (dynamic evaluation)")

def stop_rule_monitoring(rule_id):
    """
    No-op for now - disabling a rule simply prevents it from being evaluated.
    """
    current_app.logger.info(f"Rule {rule_id} disabled")

def calculate_success_rate():
    """Calculate action success rate for last 24 hours"""
    yesterday = datetime.utcnow() - timedelta(hours=24)
    
    # Apply company filter
    if current_user.role == "super_admin":
        total_actions = AlertActionLog.query.filter(
            AlertActionLog.executed_at >= yesterday
        ).count()
        
        successful_actions = AlertActionLog.query.filter(
            and_(
                AlertActionLog.executed_at >= yesterday,
                AlertActionLog.status == 'sent'
            )
        ).count()
    else:
        total_actions = AlertActionLog.query\
            .join(AlertRule)\
            .filter(
                AlertActionLog.executed_at >= yesterday,
                AlertRule.company_id == current_user.company_id
            ).count()
        
        successful_actions = AlertActionLog.query\
            .join(AlertRule)\
            .filter(
                and_(
                    AlertActionLog.executed_at >= yesterday,
                    AlertActionLog.status == 'sent',
                    AlertRule.company_id == current_user.company_id
                )
            ).count()
    
    if total_actions > 0:
        return int((successful_actions / total_actions) * 100)
    return 100

def get_recent_alerts(limit=5):
    """Get recent alerts for dashboard"""
    # Apply company filter
    if current_user.role == "super_admin":
        events = AlertEvent.query.order_by(
            AlertEvent.triggered_at.desc()
        ).limit(limit).all()
    else:
        events = AlertEvent.query\
            .join(AlertRule)\
            .filter(AlertRule.company_id == current_user.company_id)\
            .order_by(AlertEvent.triggered_at.desc())\
            .limit(limit).all()
    
    recent_alerts = []
    for event in events:
        rule = AlertRule.query.get(event.rule_id)
        device = Device.query.get(event.device_id)
        recent_alerts.append({
            'id': event.id,
            'rule_name': rule.name if rule else 'Unknown',
            'device_name': device.name if device else 'Unknown',
            'value': event.actual_value,
            'threshold': event.threshold,
            'parameter': event.parameter_type,
            'timestamp': event.triggered_at.isoformat() if event.triggered_at else None,
            'severity': rule.severity if rule else 'warning'
        })
    
    return recent_alerts

# ==========================================
# WebSocket event handlers
# ==========================================

@socketio.on('subscribe_alerts')
def handle_subscribe_alerts(data):
    """Handle client subscribing to alerts"""
    user_id = data.get('user_id')
    if user_id and current_user.is_authenticated and user_id == current_user.id:
        join_room(f"alerts_user_{user_id}")
        # Also join company room
        join_room(f"company_{current_user.company_id}")

@socketio.on('unsubscribe_alerts')
def handle_unsubscribe_alerts(data):
    """Handle client unsubscribing from alerts"""
    user_id = data.get('user_id')
    if user_id and current_user.is_authenticated and user_id == current_user.id:
        leave_room(f"alerts_user_{user_id}")
        leave_room(f"company_{current_user.company_id}")

# ==========================================
# Error handlers
# ==========================================

@alerts_bp.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@alerts_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# ==========================================
# Context processor
# ==========================================

@alerts_bp.context_processor
def inject_stats():
    """Inject stats into all templates"""
    if current_user.is_authenticated:
        unread_count = WebNotification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()
        return {'unread_notifications': unread_count}
    return {}



@alerts_bp.route("/edit_rule/<int:rule_id>", methods=["GET"])
@login_required
def edit_rule_page(rule_id):

    rule = AlertRule.query.get_or_404(rule_id)

    if current_user.role != "super_admin" and rule.company_id != current_user.company_id:
        flash("You don't have permission to edit this rule", "error")
        return redirect(url_for("alerts.rules"))

    # ✅ Parse JSON safely
    import json
    action_types = json.loads(rule.action_types) if rule.action_types else []
    action_config = json.loads(rule.action) if rule.action else {}

    # ✅ Get users for email
    users = User.query.filter_by(
        company_id=current_user.company_id,
        active_status=True
    ).all()

    # ✅ Get phone numbers for SMS
    phone_numbers = PhoneNumber.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).all()

    return render_template(
        "alerts/edit_rules.html",
        rule=rule,
        action_types=action_types,
        action_config=action_config,
        users=users,
        phone_numbers=phone_numbers
    )