from datetime import datetime
from ..extensions import get_db
from bson import ObjectId

class ProductivityModel:
    def __init__(self):
        self.collection = get_db().productivity

    def calculate_score(self, employee_id):
        # Simple weighted formula: attendance hours (50%), task completion rate (40%), late penalties (10%)
        att_coll = get_db().attendance
        task_coll = get_db().tasks
        # Attendance hours for last 30 days
        today = datetime.utcnow().date()
        start_date = (today - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        attendances = list(att_coll.find({
            'employee_id': employee_id,
            'date': {'$gte': start_date}
        }))
        total_hours = sum(a.get('working_hours', 0) for a in attendances)
        # Task completion rate
        tasks = list(task_coll.find({
            'assigned_to': employee_id,
            'created_at': {'$gte': datetime.utcnow() - datetime.timedelta(days=30)}
        }))
        completed = sum(1 for t in tasks if t.get('status') == 'completed')
        total = len(tasks) or 1
        completion_rate = completed / total
        # Late penalties
        late_count = sum(1 for a in attendances if a.get('is_late'))
        late_penalty = min(late_count / len(attendances) if attendances else 0, 1)
        # Score out of 100
        score = (min(total_hours / (30 * 8), 1) * 50) + (completion_rate * 40) - (late_penalty * 10)
        score = round(max(min(score, 100), 0), 2)
        # Upsert into productivity collection
        self.collection.update_one(
            {'employee_id': employee_id},
            {'$set': {'score': score, 'updated_at': datetime.utcnow()}},
            upsert=True
        )
        return score

    def get_score(self, employee_id):
        doc = self.collection.find_one({'employee_id': employee_id})
        return doc.get('score') if doc else None
