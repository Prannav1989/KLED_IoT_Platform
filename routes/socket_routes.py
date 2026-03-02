# socket_routes.py
from flask import request
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from datetime import datetime

def register_socket_events(socketio):
    
    # ================= CONNECTION EVENTS =================
    @socketio.on('connect')
    def handle_connect():
        print(f'✅ Client connected: {request.sid}')
        emit('connection_status', {'status': 'connected', 'sid': request.sid})
        
        # If user is authenticated, automatically join their alert room
        if current_user and current_user.is_authenticated:
            user_id = current_user.id
            room_name = f"alerts_user_{user_id}"
            join_room(room_name)
            print(f'✅ User {user_id} auto-joined room: {room_name}')
            emit('room_joined', {
                'room': room_name,
                'success': True,
                'timestamp': datetime.utcnow().isoformat()
            })

    @socketio.on('disconnect')
    def handle_disconnect():
        print(f'❌ Client disconnected: {request.sid}')

    # ================= ALERT ROOM MANAGEMENT =================
    @socketio.on('join_room')
    def handle_join_room(data):
        """Client joins their alert room"""
        user_id = data.get('user_id')
        room_type = data.get('room_type', 'alerts')
        
        if user_id:
            room_name = f"alerts_user_{user_id}"
            join_room(room_name)
            print(f'✅ User {user_id} joined room: {room_name}')
            
            # Send confirmation back to client
            emit('room_joined', {
                'room': room_name,
                'success': True,
                'timestamp': datetime.utcnow().isoformat()
            })
        else:
            print('❌ join_room: No user_id provided')
            emit('room_joined', {
                'success': False,
                'error': 'No user_id provided'
            })

    @socketio.on('leave_room')
    def handle_leave_room(data):
        """Client leaves a room"""
        user_id = data.get('user_id')
        room_type = data.get('room_type', 'alerts')
        
        if user_id:
            room_name = f"alerts_user_{user_id}"
            leave_room(room_name)
            print(f'👋 User {user_id} left room: {room_name}')

    # ================= TEST/Debug Events =================
    @socketio.on('test_alert')
    def handle_test_alert(data):
        """Handle test alert from client"""
        user_id = data.get('user_id')
        
        if user_id:
            print(f'🧪 Test alert requested for user {user_id}')
            
            test_data = {
                'title': '🧪 Test Alert',
                'message': f'This is a test alert for user {user_id}',
                'severity': 'success',
                'audio': {'sound': 'alert', 'volume': 0.5},
                'timestamp': datetime.utcnow().isoformat(),
                'is_test': True
            }
            
            # Emit to the user's room
            emit('alert_triggered', test_data, room=f'alerts_user_{user_id}')
            
            return {'success': True, 'user_id': user_id}
        
        return {'success': False, 'error': 'No user_id'}

    @socketio.on('ping')
    def handle_ping(data):
        """Handle ping from client"""
        emit('pong', {
            'timestamp': datetime.utcnow().isoformat(),
            'client_timestamp': data.get('timestamp'),
            'server': 'flask-socketio'
        })

    # ================= MQTT EVENTS (existing code) =================
    @socketio.on('publish_message')
    def handle_publish(data):
        # Lazy import to avoid circular imports
        from mqtt_manager import mqtt_manager
        
        config_id = data.get('config_id')
        topic = data.get('topic')
        message = data.get('message')
        
        if mqtt_manager.publish(config_id, topic, message):
            emit('publish_status', {'status': 'success', 'topic': topic})
        else:
            emit('publish_status', {'status': 'error', 'topic': topic})

    @socketio.on('subscribe_topic')
    def handle_subscribe(data):
        # Lazy import to avoid circular imports
        from mqtt_manager import mqtt_manager
        
        config_id = data.get('config_id')
        topic = data.get('topic')
        
        if mqtt_manager.subscribe(config_id, topic):
            emit('subscribe_status', {'status': 'success', 'topic': topic})
        else:
            emit('subscribe_status', {'status': 'error', 'topic': topic})

    print('✅ Socket.IO event handlers registered (including alert rooms)')