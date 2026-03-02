# rule_engine/loader.py
from rule_engine.cache import load_rules

def refresh(db):
    load_rules(db)
