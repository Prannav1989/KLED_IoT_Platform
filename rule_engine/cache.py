# rule_engine/cache.py

from datetime import datetime
from extensions import db
from models import AlertRule
import logging

logger = logging.getLogger(__name__)

# Simple in-memory cache
_RULE_CACHE = {}
_CACHE_LAST_LOAD = None
_CACHE_TTL_SECONDS = 30   # reload rules every 30 seconds


def get_rules(device_id: int, parameter: str):
    """
    Return a LIST of AlertRule objects
    NEVER return bool
    """

    global _RULE_CACHE, _CACHE_LAST_LOAD

    now = datetime.utcnow()

    # Reload cache if empty or TTL expired
    if (
        _CACHE_LAST_LOAD is None
        or (now - _CACHE_LAST_LOAD).total_seconds() > _CACHE_TTL_SECONDS
    ):
        logger.info("🔄 Reloading alert rule cache")

        rules = (
            AlertRule.query
            .filter(
                AlertRule.enabled == True
            )
            .all()
        )

        # Rebuild cache
        _RULE_CACHE = {}
        for rule in rules:
            key = (rule.device_id, rule.metric)
            _RULE_CACHE.setdefault(key, []).append(rule)

        _CACHE_LAST_LOAD = now
        logger.info(f"✅ Cached {len(rules)} alert rules")

    # Return rules for device + parameter
    return _RULE_CACHE.get((device_id, parameter), [])
