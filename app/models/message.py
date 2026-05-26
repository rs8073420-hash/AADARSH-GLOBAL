from datetime import datetime
from ..extensions import get_db
from bson import ObjectId

class MessageModel:
    def __init__(self):
        self.collection = get_db().messages

    def create(self, data):
        message = {
            'sender_id': data['sender_id'],
            'sender_name': data.get('sender_name', ''),
            'sender_role': data.get('sender_role', 'employee'),
            'recipient_id': data['recipient_id'],
            'recipient_name': data.get('recipient_name', ''),
            'recipient_role': data.get('recipient_role', 'employee'),
            'message': data['message'],
            'is_read': False,
            'created_at': datetime.utcnow()
        }
        return self.collection.insert_one(message)

    def get_conversation(self, user1_id, user2_id, limit=50):
        return list(self.collection.find({
            '$or': [
                {'sender_id': user1_id, 'recipient_id': user2_id},
                {'sender_id': user2_id, 'recipient_id': user1_id}
            ]
        }).sort('created_at', 1).limit(limit))

    def get_global_log(self, limit=100):
        return list(self.collection.find().sort('created_at', -1).limit(limit))

    def mark_read(self, sender_id, recipient_id):
        # Mark all messages from sender_id to recipient_id as read
        return self.collection.update_many(
            {'sender_id': sender_id, 'recipient_id': recipient_id, 'is_read': False},
            {'$set': {'is_read': True}}
        )

    def count_unread(self, recipient_id):
        return self.collection.count_documents({'recipient_id': recipient_id, 'is_read': False})

    def count_unread_from_sender(self, sender_id, recipient_id):
        return self.collection.count_documents({'sender_id': sender_id, 'recipient_id': recipient_id, 'is_read': False})
