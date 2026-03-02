from datetime import datetime, timezone

def relative_time(value):
    if not value:
        return "Never"

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            return value

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - value
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def register_jinja_filters(app):
    app.jinja_env.filters["relative_time"] = relative_time
