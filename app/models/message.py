from datetime import datetime
from ..extensions import get_db
from bson import ObjectId

class ChatRoomModel:
    def __init__(self):
        self.collection = get_db().chat_rooms

    def create_room(self, data):
        room = {
            'type': data.get('type', 'direct'), # direct, group, lead, task
            'name': data.get('name', ''),
            'reference_id': data.get('reference_id', ''), # ID of lead or task if applicable
            'members': data.get('members', []), # list of user IDs
            'created_by': data.get('created_by', ''),
            'created_at': datetime.utcnow(),
            'last_message_at': datetime.utcnow(),
            'last_message_snippet': '',
            'is_active': True
        }
        return self.collection.insert_one(room)

    def get_user_rooms(self, user_id):
        return list(self.collection.find({'members': user_id}).sort('last_message_at', -1))

    def get_room_by_id(self, room_id):
        return self.collection.find_one({'_id': ObjectId(room_id)})

    def get_direct_room(self, user1_id, user2_id):
        return self.collection.find_one({
            'type': 'direct',
            'members': {'$all': [user1_id, user2_id], '$size': 2}
        })
        
    def get_room_by_reference(self, ref_type, ref_id):
        return self.collection.find_one({
            'type': ref_type,
            'reference_id': ref_id
        })

    def update_last_message(self, room_id, snippet):
        return self.collection.update_one(
            {'_id': ObjectId(room_id)},
            {'$set': {'last_message_at': datetime.utcnow(), 'last_message_snippet': snippet}}
        )

class MessageModel:
    def __init__(self):
        self.collection = get_db().messages

    # --- LEGACY METHODS (Kept for safety) ---
    def create(self, data):
        message = {
            'sender_id': data['sender_id'],
            'sender_name': data.get('sender_name', ''),
            'sender_role': data.get('sender_role', 'employee'),
            'recipient_id': data.get('recipient_id', ''),
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
        return self.collection.update_many(
            {'sender_id': sender_id, 'recipient_id': recipient_id, 'is_read': False},
            {'$set': {'is_read': True}}
        )

    def count_unread(self, recipient_id):
        return self.collection.count_documents({'recipient_id': recipient_id, 'is_read': False})

    def count_unread_from_sender(self, sender_id, recipient_id):
        return self.collection.count_documents({'sender_id': sender_id, 'recipient_id': recipient_id, 'is_read': False})

    # --- V2 METHODS ---
    def create_v2(self, data):
        message = {
            'room_id': data['room_id'],
            'sender_id': data['sender_id'],
            'sender_name': data.get('sender_name', ''),
            'message': data.get('message', ''),
            'reply_to': data.get('reply_to', None), # message ID if reply
            'attachments': data.get('attachments', []), # list of {url, type, name}
            'reactions': {}, # dict of {emoji: [user_ids]}
            'seen_by': [data['sender_id']],
            'status': 'sent', # sent, delivered, seen
            'created_at': datetime.utcnow()
        }
        return self.collection.insert_one(message)

    def get_room_messages(self, room_id, limit=50, skip=0):
        return list(self.collection.find({'room_id': room_id}).sort('created_at', -1).skip(skip).limit(limit))

    def add_reaction(self, message_id, emoji, user_id):
        # We use a simple pull then push to ensure uniqueness if doing this purely in mongo, 
        # but to keep it lightweight we'll do it manually or via a clever update.
        # Actually, adding to set is easiest.
        field = f'reactions.{emoji}'
        return self.collection.update_one(
            {'_id': ObjectId(message_id)},
            {'$addToSet': {field: user_id}}
        )

    def remove_reaction(self, message_id, emoji, user_id):
        field = f'reactions.{emoji}'
        return self.collection.update_one(
            {'_id': ObjectId(message_id)},
            {'$pull': {field: user_id}}
        )

    def mark_room_seen(self, room_id, user_id):
        return self.collection.update_many(
            {'room_id': room_id, 'seen_by': {'$ne': user_id}},
            {'$addToSet': {'seen_by': user_id}, '$set': {'status': 'seen'}}
        )

    def get_unread_rooms_count(self, user_id, room_ids):
        # Count how many rooms have at least one message not seen by user
        pipeline = [
            {'$match': {'room_id': {'$in': room_ids}, 'seen_by': {'$ne': user_id}}},
            {'$group': {'_id': '$room_id'}}
        ]
        res = list(self.collection.aggregate(pipeline))
        return len(res)
