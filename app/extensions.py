from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient, ASCENDING, DESCENDING

jwt = JWTManager()
socketio = SocketIO()
cors = CORS()
limiter = Limiter(key_func=get_remote_address)

mongo_client = None
db = None

def init_db(app):
    global mongo_client, db
    mongo_client = MongoClient(app.config['MONGO_URI'])
    db = mongo_client.get_default_database()
    # Existing indexes
    db.employees.create_index('employee_id', unique=True)
    db.employees.create_index('mobile')
    db.tasks.create_index('task_id', unique=True)
    db.attendance.create_index([('employee_id', 1), ('date', 1)])
    db.messages.create_index('sender_id')
    db.messages.create_index('recipient_id')
    # Task module performance indexes
    db.tasks.create_index([('status', ASCENDING)])
    db.tasks.create_index([('priority', ASCENDING)])
    db.tasks.create_index([('assigned_to', ASCENDING)])
    db.tasks.create_index([('due_date', ASCENDING)])
    db.tasks.create_index([('created_at', DESCENDING)])
    # New collections indexes
    db.leads.create_index('phone', unique=True)
    db.leads.create_index('assigned_to')
    db.leads.create_index('status')
    db.leads.create_index('created_at')
    db.notifications.create_index('recipient_id')
    db.notifications.create_index('is_read')
    db.activity_logs.create_index('employee_id')
    db.activity_logs.create_index('timestamp')
    db.gamification.create_index('employee_id')
    db.gamification.create_index('badge')
    db.calendar_events.create_index('assigned_to')
    db.calendar_events.create_index('start')
    db.calendar_events.create_index('end')
    db.notes.create_index('employee_id')
    db.productivity.create_index('employee_id')
    return db

def get_db():
    return db
