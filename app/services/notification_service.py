from ..models.notification import NotificationModel

class NotificationService:
    def __init__(self):
        self.model = NotificationModel()

    def send(self, recipient_id, title, message, notif_type='info', sender_id='', sender_name='Admin', recipient_role='employee'):
        data = {
            'title': title,
            'message': message,
            'recipient_id': recipient_id,
            'recipient_role': recipient_role,
            'sender_id': sender_id,
            'sender_name': sender_name,
            'type': notif_type
        }
        result = self.model.create(data)
        
        # Local import to avoid circular dependency
        from ..extensions import socketio
        socketio.emit('new_notification', {
            'title': title,
            'message': message,
            'type': notif_type
        }, room=recipient_id)
        return result

    def broadcast_to_role(self, role, title, message, notif_type='info'):
        from ..extensions import get_db
        db = get_db()
        if role == 'employee':
            users = list(db.employees.find({'is_active': True}, {'_id': 1}))
        else:
            users = list(db.admins.find({}, {'_id': 1}))
        for user in users:
            self.send(str(user['_id']), title, message, notif_type, recipient_role=role)
