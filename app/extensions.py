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
    return db

def get_db():
    return db
