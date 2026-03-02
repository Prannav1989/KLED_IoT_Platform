# rule_engine/engine.py

from datetime import datetime
from rule_engine.cache import get_rules


def evaluate(device_id, parameter, value, db):
    """
    Evaluate alert rules for a single sensor value
    """
    rules = get_rules(device_id, parameter) or []

    if not isinstance(rules, (list, tuple)):
        print(f"⚠️ get_rules returned invalid type: {type(rules)}")
        return

    if not rules:
        return

    now = datetime.utcnow()
    triggered_rules = []

    for rule in rules:
        try:
            # ---------------------------
            # Cooldown check
            # ---------------------------
            if rule.last_triggered:
                elapsed = (now - rule.last_triggered).total_seconds()
                if elapsed < rule.cooldown_seconds:
                    continue

            # ---------------------------
            # Condition check
            # ---------------------------
            if compare(value, rule.operator, rule.threshold):
                triggered_rules.append(rule)

        except Exception as e:
            print(f"❌ Rule evaluation error ({getattr(rule, 'id', 'unknown')}): {e}")

    # Process triggered rules with database updates
    for rule in triggered_rules:
        try:
            create_event(rule, value, db, now)
        except Exception as e:
            print(f"❌ Failed to create event for rule {getattr(rule, 'id', 'unknown')}: {e}")


def compare(v, op, t):
    """
    Compare value against threshold using operator
    """
    if op == ">":
        return v > t
    if op == "<":
        return v < t
    if op == ">=":
        return v >= t
    if op == "<=":
        return v <= t
    if op == "==":
        return v == t
    return False


def create_event(rule, value, db, trigger_time):
    """
    Persist alert event + update cooldown timestamp
    """
    from models import AlertEvent

    try:
        if rule.metric is None:
            raise ValueError("rule.metric is None")

        event = AlertEvent(
            rule_id=int(rule.id),
            device_id=int(rule.device_id),
            parameter_type=str(rule.metric),
            actual_value=float(value),
            threshold=float(rule.threshold),
            triggered_at=trigger_time,
            status="triggered",
            source="mqtt"
        )

        db.session.add(event)

        # Update cooldown safely
        rule.last_triggered = trigger_time

        db.session.commit()

        print(
            f"🚨 ALERT TRIGGERED | "
            f"Rule='{rule.name}' | "
            f"Device={rule.device_id} | "
            f"Value={value}"
        )

    except Exception as e:
        db.session.rollback()
        print(f"❌ Failed to create alert_event: {e}")
        return
