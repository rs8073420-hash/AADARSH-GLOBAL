from datetime import datetime
from ..extensions import get_db
from bson import ObjectId

class ActivityLogModel:
    def __init__(self):
        self.collection = get_db().activity_logs

    def log(self, employee_id, action, page=None):
        entry = {
            'employee_id': employee_id,
            'action': action,
            'page': page,
            'timestamp': datetime.utcnow()
        }
        return self.collection.insert_one(entry)

    def get_recent(self, employee_id, limit=50):
        return list(self.collection.find({'employee_id': employee_id}).sort('timestamp', -1).limit(limit))

    def get_all_online(self, since_minutes=5):
        cutoff = datetime.utcnow() - datetime.timedelta(minutes=since_minutes)
        return list(self.collection.find({'timestamp': {'$gte': cutoff}}))
