from flask import Blueprint, render_template
from flask_login import login_required, current_user

support_bp = Blueprint('support', __name__)

@support_bp.route('/support')
@login_required
def support_home():
    """Simple placeholder until full support system is built."""
    return render_template('dashboard/support.html', current_user=current_user)
