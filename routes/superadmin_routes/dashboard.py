# # dashboard_bp.py
# from flask import Blueprint, render_template, jsonify, request, session
# from dashboard import Dashboard  # Import your Dashboard class
# import os

# # Create Blueprint
# dashboard_bp = Blueprint('dashboard', __name__, 
#                         template_folder='templates',
#                         static_folder='static',
#                         url_prefix='/dashboard')

# # Initialize dashboard (you might want to do this differently in production)
# db_path = os.path.join(os.path.dirname(__file__), 'your_database.db')
# dashboard = Dashboard(db_path)

# @dashboard_bp.route('/')
# def dashboard_home():
#     """Main dashboard page"""
#     user_id = session.get('user_id')
#     if not user_id:
#         return jsonify({'error': 'Unauthorized'}), 401
    
#     companies = dashboard.get_user_companies(user_id)
#     summary = dashboard.get_dashboard_summary(user_id)
    
#     return render_template('dashboard.html', 
#                          companies=companies, 
#                          summary=summary)

# @dashboard_bp.route('/company/<int:company_id>/sensors')
# def company_sensors(company_id):
#     """Get sensors for a specific company"""
#     user_id = session.get('user_id')
#     if not user_id:
#         return jsonify({'error': 'Unauthorized'}), 401
    
#     sensors = dashboard.get_company_sensors(company_id, user_id)
#     return jsonify({'sensors': sensors})

# @dashboard_bp.route('/sensor/<int:sensor_id>/data')
# def sensor_data(sensor_id):
#     """Get data for a specific sensor"""
#     user_id = session.get('user_id')
#     if not user_id:
#         return jsonify({'error': 'Unauthorized'}), 401
    
#     time_range = request.args.get('time_range', '24h')
#     limit = int(request.args.get('limit', 100))
    
#     data = dashboard.get_sensor_data(sensor_id, user_id, time_range, limit)
#     return jsonify({'data': data})

# @dashboard_bp.route('/summary')
# def dashboard_summary():
#     """Get dashboard summary"""
#     user_id = session.get('user_id')
#     if not user_id:
#         return jsonify({'error': 'Unauthorized'}), 401
    
#     summary = dashboard.get_dashboard_summary(user_id)
#     return jsonify(summary)

# @dashboard_bp.route('/recent-readings')
# def recent_readings():
#     """Get recent sensor readings"""
#     user_id = session.get('user_id')
#     if not user_id:
#         return jsonify({'error': 'Unauthorized'}), 401
    
#     limit = int(request.args.get('limit', 10))
#     readings = dashboard.get_recent_sensor_readings(user_id, limit)
#     return jsonify({'readings': readings})