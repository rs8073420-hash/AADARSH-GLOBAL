from datetime import datetime
from ..extensions import get_db
from bson import ObjectId
import pymongo

class LeadAssignmentLogModel:
    def __init__(self):
        self.collection = get_db().lead_assignment_logs
        self._ensure_indexes()

    def _ensure_indexes(self):
        try:
            self.collection.create_index([("lead_id", pymongo.ASCENDING)])
            self.collection.create_index([("assigned_to", pymongo.ASCENDING)])
            self.collection.create_index([("assigned_at", pymongo.ASCENDING)])
        except Exception:
            pass

    def log_assignment(self, lead_id, assigned_to, assigned_from="SYSTEM", reassigned=False, reason="", lead_name="", priority="", action_type=""):
        log_entry = {
            'lead_id': str(lead_id),
            'lead_name': lead_name,
            'priority': priority,
            'action_type': action_type or ('Reassignment' if reassigned else 'Initial Assignment'),
            'assigned_from': str(assigned_from),
            'assigned_to': str(assigned_to),
            'assigned_at': datetime.utcnow(),
            'reassigned': reassigned,
            'reassigned_reason': reason,
            'updated_by_employee': False,
            'employee_response_time': 0, # in seconds
        }
        return self.collection.insert_one(log_entry)
        
    def mark_employee_response(self, lead_id, employee_id):
        # Find the latest assignment for this lead to this employee
        latest = self.collection.find_one(
            {'lead_id': str(lead_id), 'assigned_to': str(employee_id), 'updated_by_employee': False},
            sort=[('assigned_at', -1)]
        )
        if latest:
            response_time = (datetime.utcnow() - latest['assigned_at']).total_seconds()
            self.collection.update_one(
                {'_id': latest['_id']},
                {'$set': {
                    'updated_by_employee': True,
                    'employee_response_time': response_time
                }}
            )

    def get_logs_for_lead(self, lead_id):
        return list(self.collection.find({'lead_id': str(lead_id)}).sort('assigned_at', -1))
