from datetime import datetime
from ..extensions import get_db
from bson import ObjectId
import pymongo

class LeadModel:
    def __init__(self):
        self.collection = get_db().leads_master
        self._ensure_indexes()

    def _ensure_indexes(self):
        # Create background indexes for performance
        try:
            self.collection.create_index([("phone", pymongo.ASCENDING)], unique=True, sparse=True)
            self.collection.create_index([("assigned_to", pymongo.ASCENDING)])
            self.collection.create_index([("status", pymongo.ASCENDING)])
            self.collection.create_index([("assigned_at", pymongo.ASCENDING)])
            self.collection.create_index([("priority", pymongo.ASCENDING)])
            self.collection.create_index([("created_at", pymongo.DESCENDING)])
        except Exception:
            pass # Index might already exist

    def create(self, data):
        lead = {
            'name': data.get('name', ''),
            'phone': data.get('phone', ''),
            'email': data.get('email', ''),
            'city': data.get('city', ''),
            'budget': data.get('budget', ''),
            'source': data.get('source', ''),
            'notes': data.get('notes', ''),
            'priority': data.get('priority', 'Medium'),
            'auto_reassign': data.get('auto_reassign', True),
            'reassign_interval_minutes': data.get('reassign_interval_minutes', 1440),
            'assigned_to': data.get('assigned_to', ''),
            'status': data.get('status', 'New'),
            'assigned_at': datetime.utcnow() if data.get('assigned_to') else None,
            'last_updated_at': datetime.utcnow(),
            'followup_at': data.get('followup_at', None),
            'lead_score': 0,
            'reassigned_count': 0,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        return self.collection.insert_one(lead)

    def get_all(self, filters=None, page=1, limit=20):
        if filters is None:
            filters = {}
        skips = limit * (page - 1)
        cursor = self.collection.find(filters).skip(skips).limit(limit).sort('created_at', -1)
        return list(cursor)
        
    def find_by_phone(self, phone):
        return self.collection.find_one({'phone': phone})
        
    def find_by_id(self, lead_id):
        return self.collection.find_one({'_id': ObjectId(lead_id)})

    def update(self, lead_id, data):
        data['updated_at'] = datetime.utcnow()
        data['last_updated_at'] = datetime.utcnow()
        return self.collection.update_one({'_id': ObjectId(lead_id)}, {'$set': data})
        
    def reassign(self, lead_id, new_employee_id, reason="Auto-reassignment"):
        return self.collection.update_one(
            {'_id': ObjectId(lead_id)},
            {
                '$set': {
                    'assigned_to': new_employee_id,
                    'assigned_at': datetime.utcnow(),
                    'last_updated_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                },
                '$inc': {'reassigned_count': 1}
            }
        )

    def delete(self, lead_id):
        return self.collection.delete_one({'_id': ObjectId(lead_id)})

    def count(self, filters=None):
        if filters is None:
            filters = {}
        return self.collection.count_documents(filters)
