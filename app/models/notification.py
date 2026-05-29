from datetime import datetime
from ..extensions import get_db
from bson import ObjectId

class NotificationModel:
    def __init__(self):
        self.collection = get_db().notifications

    def create(self, recipient_id, notif_type, payload):
        notif = {
            'recipient_id': recipient_id,
            'type': notif_type,
            'payload': payload,
            'is_read': False,
            'created_at': datetime.utcnow()
        }
        return self.collection.insert_one(notif)

    def get_unread(self, recipient_id, limit=20):
        return list(self.collection.find({'recipient_id': recipient_id, 'is_read': False})
                    .sort('created_at', -1).limit(limit))

    def mark_read(self, notif_id):
        return self.collection.update_one({'_id': ObjectId(notif_id)}, {'$set': {'is_read': True}})

    def mark_all_read(self, recipient_id):
        return self.collection.update_many({'recipient_id': recipient_id}, {'$set': {'is_read': True}})

    def get_all(self, recipient_id, limit=50):
        return list(self.collection.find({'recipient_id': recipient_id})
                    .sort('created_at', -1).limit(limit))
