# auth.py
from flask_login import LoginManager
from models import User, db

login_manager = LoginManager()
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def init_auth(app):
    login_manager.init_app(app)