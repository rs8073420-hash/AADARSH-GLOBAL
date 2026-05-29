from datetime import datetime
from ..extensions import get_db
from bson import ObjectId

class AttachmentModel:
    def __init__(self):
        self.collection = get_db().attachments

    def create(self, data):
        attachment = {
            'message_id': data.get('message_id'),
            'room_id': data.get('room_id'),
            'sender_id': data.get('sender_id'),
            'file_name': data.get('file_name'),
            'file_type': data.get('file_type'),
            'file_size': data.get('file_size'),
            'file_path': data.get('file_path'),
            'uploaded_at': datetime.utcnow()
        }
        return self.collection.insert_one(attachment)
        
    def get_by_id(self, attachment_id):
        return self.collection.find_one({'_id': ObjectId(attachment_id)})
