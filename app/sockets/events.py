from flask_socketio import emit, join_room, leave_room, disconnect
from flask_jwt_extended import decode_token

def register_events(socketio):

    @socketio.on('connect')
    def on_connect(auth):
        try:
            token = auth.get('token') if auth else None
            if not token:
                disconnect()
                return
            decoded = decode_token(token)
            user_id = decoded['sub']
            role = decoded.get('role', 'employee')
            join_room(user_id)
            join_room(role)
            emit('connected', {'message': 'Connected to real-time server', 'user_id': user_id})
        except Exception as e:
            disconnect()

    @socketio.on('disconnect')
    def on_disconnect():
        pass

    @socketio.on('join_room')
    def on_join(data):
        room = data.get('room')
        if room:
            join_room(room)
            emit('room_joined', {'room': room})

    @socketio.on('leave_room')
    def on_leave(data):
        room = data.get('room')
        if room:
            leave_room(room)

    @socketio.on('join_task_room')
    def on_join_task(data):
        task_id = data.get('task_id')
        if task_id:
            room = f'task_{task_id}'
            join_room(room)
            emit('room_joined', {'room': room})

    @socketio.on('leave_task_room')
    def on_leave_task(data):
        task_id = data.get('task_id')
        if task_id:
            leave_room(f'task_{task_id}')

    @socketio.on('ping')
    def on_ping():
        emit('pong', {'status': 'ok'})
