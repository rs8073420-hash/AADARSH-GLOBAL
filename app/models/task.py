from datetime import datetime
from ..extensions import get_db
from bson import ObjectId
import random, string, uuid

class TaskModel:
    def __init__(self):
        self.collection = get_db().tasks

    def generate_task_id(self):
        chars = string.ascii_uppercase + string.digits
        return 'TSK-' + ''.join(random.choices(chars, k=6))

    def create(self, data):
        now = datetime.utcnow()
        task = {
            'task_id': self.generate_task_id(),
            'title': data['title'],
            'description': data.get('description', ''),
            'priority': data.get('priority', 'medium'),
            'status': data.get('status', 'assigned'),
            'assigned_to': data.get('assigned_to', []),
            'assigned_by': data.get('assigned_by', ''),
            'assigned_by_name': data.get('assigned_by_name', 'Admin'),
            'due_date': data.get('due_date', ''),
            'due_time': data.get('due_time', ''),
            'remarks': data.get('remarks', ''),
            'admin_remarks': data.get('admin_remarks', ''),
            'created_at': now,
            'updated_at': now,
            'completed_at': None,
            'progress': 0,
            'messages': [],
            'comments': [],
            'attachments': [],
            'activity_logs': [
                {
                    'log_id': str(uuid.uuid4()),
                    'action': 'task_created',
                    'description': 'Task created and assigned',
                    'by_id': data.get('assigned_by', ''),
                    'by_name': data.get('assigned_by_name', 'Admin'),
                    'by_role': 'admin',
                    'timestamp': now.isoformat()
                }
            ],
            'reassigned_history': [],
            'created_by': data.get('assigned_by', ''),
        }
        return self.collection.insert_one(task)

    def find_by_id(self, task_id):
        return self.collection.find_one({'_id': ObjectId(task_id)})

    def find_by_task_id(self, task_id):
        return self.collection.find_one({'task_id': task_id})

    def get_all(self, filters={}):
        return list(self.collection.find(filters).sort('created_at', -1))

    def get_for_employee(self, employee_id):
        return list(self.collection.find({'assigned_to': employee_id}).sort('created_at', -1))

    def update(self, task_id, data):
        data['updated_at'] = datetime.utcnow()
        if data.get('status') == 'completed' and 'completed_at' not in data:
            data['completed_at'] = datetime.utcnow()
        res = self.collection.update_one({'_id': ObjectId(task_id)}, {'$set': data})
        try:
            from ..extensions import socketio
            socketio.emit('dashboard_update', {'type': 'task', 'task_id': str(task_id)})
            socketio.emit('activity_logged', {'type': 'task_updated', 'task_id': str(task_id)})
        except:
            pass
        return res

    def add_comment(self, task_id, comment):
        comment['comment_id'] = str(uuid.uuid4())
        comment['timestamp'] = datetime.utcnow().isoformat()
        return self.collection.update_one(
            {'_id': ObjectId(task_id)},
            {'$push': {'comments': comment}, '$set': {'updated_at': datetime.utcnow()}}
        )

    def add_attachment(self, task_id, attachment):
        attachment['attachment_id'] = str(uuid.uuid4())
        attachment['timestamp'] = datetime.utcnow().isoformat()
        return self.collection.update_one(
            {'_id': ObjectId(task_id)},
            {'$push': {'attachments': attachment}, '$set': {'updated_at': datetime.utcnow()}}
        )

    def add_activity_log(self, task_id, log):
        log['log_id'] = str(uuid.uuid4())
        log['timestamp'] = datetime.utcnow().isoformat()
        return self.collection.update_one(
            {'_id': ObjectId(task_id)},
            {'$push': {'activity_logs': log}, '$set': {'updated_at': datetime.utcnow()}}
        )

    def add_message(self, task_id, message):
        return self.collection.update_one(
            {'_id': ObjectId(task_id)},
            {'$push': {'messages': message}}
        )

    def reassign(self, task_id, new_assigned_to, reassigned_by_id, reassigned_by_name, note=''):
        now = datetime.utcnow()
        task = self.find_by_id(task_id)
        if not task:
            return None
        old_assigned = task.get('assigned_to', [])
        history_entry = {
            'from': old_assigned,
            'to': new_assigned_to,
            'by_id': reassigned_by_id,
            'by_name': reassigned_by_name,
            'note': note,
            'timestamp': now.isoformat()
        }
        return self.collection.update_one(
            {'_id': ObjectId(task_id)},
            {
                '$set': {'assigned_to': new_assigned_to, 'updated_at': now},
                '$push': {'reassigned_history': history_entry}
            }
        )

    def get_kanban_data(self, filters={}):
        statuses = ['assigned', 'in_progress', 'under_review', 'approved', 'rejected', 'completed']
        result = {s: [] for s in statuses}
        all_tasks = self.get_all(filters)
        for task in all_tasks:
            status = task.get('status', 'assigned')
            if status in result:
                result[status].append(task)
            else:
                result['assigned'].append(task)
        return result

    def delete(self, task_id):
        return self.collection.delete_one({'_id': ObjectId(task_id)})

    def count(self, filters={}):
        return self.collection.count_documents(filters)

    def get_analytics(self):
        from datetime import date
        pipeline_status = [{'$group': {'_id': '$status', 'count': {'$sum': 1}}}]
        pipeline_priority = [{'$group': {'_id': '$priority', 'count': {'$sum': 1}}}]
        pipeline_employee = [
            {'$unwind': '$assigned_to'},
            {'$group': {'_id': '$assigned_to', 'count': {'$sum': 1}}}
        ]
        status_counts = list(self.collection.aggregate(pipeline_status))
        priority_counts = list(self.collection.aggregate(pipeline_priority))
        employee_counts = list(self.collection.aggregate(pipeline_employee))
        today = date.today().isoformat()
        overdue = self.collection.count_documents({
            'due_date': {'$lt': today, '$ne': ''},
            'status': {'$nin': ['completed', 'approved']}
        })
        return {
            'by_status': {s['_id']: s['count'] for s in status_counts if s['_id']},
            'by_priority': {p['_id']: p['count'] for p in priority_counts if p['_id']},
            'by_employee': {e['_id']: e['count'] for e in employee_counts if e['_id']},
            'overdue': overdue,
            'total': self.count()
        }
