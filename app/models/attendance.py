from datetime import datetime, date
from ..extensions import get_db
from bson import ObjectId

class AttendanceModel:
    def __init__(self):
        self.collection = get_db().attendance

    def check_in(self, employee_id, employee_name, remarks=""):
        today = date.today().strftime('%Y-%m-%d')
        now = datetime.utcnow()
        
        existing = self.collection.find_one({'employee_id': employee_id, 'date': today})
        
        if existing:
            res = self.collection.update_one(
                {'_id': existing['_id']},
                {'$set': {'check_out': None, 'last_session_start': now}}
            )
        else:
            record = {
                'employee_id': employee_id,
                'employee_name': employee_name,
                'date': today,
                'check_in': now,
                'last_session_start': now,
                'check_out': None,
                'working_hours': 0,
                'status': 'present',
                'is_late': self._is_late(now),
                'is_half_day': False,
                'early_exit': False,
                'overtime': False,
                'completed_tasks': 0,
                'pending_tasks': 0,
                'productivity_percentage': 0.0,
                'remarks': remarks,
                'tomorrow_plan': '',
                'created_at': now
            }
            res = self.collection.insert_one(record)
            
        try:
            from ..extensions import socketio
            socketio.emit('dashboard_update', {'type': 'attendance', 'action': 'check_in', 'employee_id': employee_id})
            socketio.emit('activity_logged', {'type': 'check_in', 'employee_name': employee_name})
        except:
            pass
        return res

    def check_out(self, record, remarks="", tomorrow_plan="", completed_tasks=0, pending_tasks=0, productivity=0.0):
        now = datetime.utcnow()
        session_start = record.get('last_session_start', record.get('check_in'))
        if session_start is None:
            session_start = now # Fail safe
            
        duration = now - session_start
        session_hours = duration.total_seconds() / 3600
        new_working_hours = round(record.get('working_hours', 0) + session_hours, 2)
        
        # Calculate IST time
        from datetime import timedelta
        ist = now + timedelta(hours=5, minutes=30)
        
        # Early exit if checked out before 19:00 (7 PM) IST
        early_exit = ist.hour < 19
        
        # Overtime if checked out after 19:30 (7:30 PM) IST
        overtime = ist.hour > 19 or (ist.hour == 19 and ist.minute > 30)
        
        # Half day if total working hours < 8
        is_half_day = new_working_hours < 8.0
        
        res = self.collection.update_one(
            {'_id': record['_id']},
            {'$set': {
                'check_out': now, 
                'working_hours': new_working_hours, 
                'is_half_day': is_half_day,
                'remarks': remarks, 
                'tomorrow_plan': tomorrow_plan,
                'early_exit': early_exit,
                'overtime': overtime,
                'completed_tasks': completed_tasks,
                'pending_tasks': pending_tasks,
                'productivity_percentage': productivity
            }}
        )
        try:
            from ..extensions import socketio
            socketio.emit('dashboard_update', {'type': 'attendance', 'action': 'check_out'})
            socketio.emit('activity_logged', {'type': 'check_out'})
        except:
            pass
        return res

    def _is_late(self, utc_time):
        from datetime import timedelta
        ist = utc_time + timedelta(hours=5, minutes=30)
        # Late if checked in after 10:00 AM IST
        if ist.hour > 10 or (ist.hour == 10 and ist.minute > 0):
            return True
        return False

    def get_today_record(self, employee_id):
        today = date.today().strftime('%Y-%m-%d')
        return self.collection.find_one({'employee_id': employee_id, 'date': today})

    def get_history(self, employee_id, limit=30):
        return list(self.collection.find(
            {'employee_id': employee_id}
        ).sort('date', -1).limit(limit))

    def get_today_all(self):
        today = date.today().strftime('%Y-%m-%d')
        return list(self.collection.find({'date': today}))

    def get_by_date_range(self, start, end, employee_id=None):
        query = {'date': {'$gte': start, '$lte': end}}
        if employee_id:
            query['employee_id'] = employee_id
        return list(self.collection.find(query).sort('date', -1))

    def count_today_present(self):
        today = date.today().strftime('%Y-%m-%d')
        return self.collection.count_documents({'date': today})

    def count_today_late(self):
        today = date.today().strftime('%Y-%m-%d')
        return self.collection.count_documents({'date': today, 'is_late': True})

    def count_today_overtime(self):
        today = date.today().strftime('%Y-%m-%d')
        return self.collection.count_documents({'date': today, 'overtime': True})

    def get_monthly_summary(self, employee_id, year, month):
        # Format string matching YYYY-MM
        prefix = f"{year}-{month:02d}"
        records = list(self.collection.find({
            'employee_id': employee_id,
            'date': {'$regex': f"^{prefix}"}
        }))
        return records
