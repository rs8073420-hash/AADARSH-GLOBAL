from flask_socketio import emit, join_room, leave_room, disconnect
from flask_jwt_extended import decode_token
from datetime import datetime

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

    # ===================================================================
    # ENHANCED SOCKET EVENTS
    # ===================================================================

    # --- Typing Indicator ---
    @socketio.on('typing')
    def on_typing(data):
        """Broadcast typing indicator to the recipient."""
        try:
            recipient_id = data.get('recipient_id')
            sender_id = data.get('sender_id', '')
            sender_name = data.get('sender_name', '')
            is_typing = data.get('is_typing', True)
            if recipient_id:
                emit('typing_indicator', {
                    'sender_id': sender_id,
                    'sender_name': sender_name,
                    'is_typing': is_typing,
                }, room=recipient_id)
        except Exception:
            pass

    # --- Message Seen ---
    @socketio.on('message_seen')
    def on_message_seen(data):
        """Mark a message as seen and notify the sender."""
        try:
            message_id = data.get('message_id')
            sender_id = data.get('sender_id')
            seen_by = data.get('seen_by', '')
            seen_by_name = data.get('seen_by_name', '')
            if message_id and sender_id:
                # Update in DB
                from app.extensions import get_db
                db = get_db()
                from bson import ObjectId
                db.messages.update_one(
                    {'_id': ObjectId(message_id)},
                    {'$set': {'is_seen': True, 'seen_at': datetime.utcnow()}}
                )
                # Notify the sender
                emit('message_seen_ack', {
                    'message_id': message_id,
                    'seen_by': seen_by,
                    'seen_by_name': seen_by_name,
                    'seen_at': datetime.utcnow().isoformat() + 'Z',
                }, room=sender_id)
        except Exception:
            pass

    # --- Activity Heartbeat (via socket) ---
    @socketio.on('activity_heartbeat')
    def on_activity_heartbeat(data):
        """Update employee activity status via socket (alternative to REST heartbeat)."""
        try:
            employee_id = data.get('employee_id')
            current_page = data.get('current_page', '')
            action = data.get('action', 'heartbeat')
            employee_name = data.get('employee_name', '')
            if employee_id:
                from app.extensions import get_db
                db = get_db()
                now = datetime.utcnow()
                db.activity_status.update_one(
                    {'employee_id': employee_id},
                    {'$set': {
                        'employee_id': employee_id,
                        'employee_name': employee_name,
                        'current_page': current_page,
                        'last_action': action,
                        'last_heartbeat': now,
                    }},
                    upsert=True
                )
                # Broadcast to admin room
                emit('employee_activity_update', {
                    'employee_id': employee_id,
                    'employee_name': employee_name,
                    'current_page': current_page,
                    'action': action,
                    'timestamp': now.isoformat() + 'Z',
                }, room='admin')
        except Exception:
            pass

    # --- Lead Room Events ---
    @socketio.on('join_lead_room')
    def on_join_lead(data):
        """Join a specific lead's room for real-time collaboration."""
        lead_id = data.get('lead_id')
        if lead_id:
            room = f'lead_{lead_id}'
            join_room(room)
            emit('room_joined', {'room': room})

    @socketio.on('leave_lead_room')
    def on_leave_lead(data):
        """Leave a lead's room."""
        lead_id = data.get('lead_id')
        if lead_id:
            leave_room(f'lead_{lead_id}')

    # --- Notification Events ---
    @socketio.on('subscribe_notifications')
    def on_subscribe_notifications(data):
        """
        Client subscribes to their notification channel.
        They already join their user_id room on connect, so this is
        mostly an explicit acknowledgment for the frontend.
        """
        user_id = data.get('user_id')
        if user_id:
            join_room(user_id)
            emit('notifications_subscribed', {'user_id': user_id})

    @socketio.on('mark_notification_read')
    def on_mark_notification_read(data):
        """Mark a notification as read via socket (convenience)."""
        try:
            notif_id = data.get('notification_id')
            recipient_id = data.get('recipient_id')
            if notif_id:
                from app.extensions import get_db
                from bson import ObjectId
                db = get_db()
                db.notifications.update_one(
                    {'_id': ObjectId(notif_id)},
                    {'$set': {'is_read': True}}
                )
                if recipient_id:
                    # Send updated unread count
                    count = db.notifications.count_documents({
                        'recipient_id': recipient_id,
                        'is_read': False
                    })
                    emit('unread_count_update', {'unread_count': count}, room=recipient_id)
        except Exception:
            pass

    def auto_reassign_leads_daemon():
        from app.services.lead_engine import LeadEngine
        import time
        # wait a bit for app to fully initialize
        socketio.sleep(5)
        try:
            engine = LeadEngine()
        except Exception as e:
            print("Failed to init LeadEngine:", e)
            return

        while True:
            socketio.sleep(60)
            try:
                engine.check_and_reassign_stale_leads()
            except Exception as e:
                print(f"Lead Engine Daemon Error: {e}")

    socketio.start_background_task(auto_reassign_leads_daemon)
