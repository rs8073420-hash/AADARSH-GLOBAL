from datetime import datetime
from ..extensions import get_db
import bcrypt

class AdminModel:
    def __init__(self):
        self.collection = get_db().admins

    def create_admin(self, data):
        hashed = bcrypt.hashpw(data['password'].encode(), bcrypt.gensalt())
        admin = {
            'name': data['name'],
            'email': data.get('email', ''),
            'mobile': data['mobile'],
            'employee_id': data['employee_id'],
            'password': hashed,
            'role': 'admin',
            'avatar': data.get('avatar', ''),
            'created_at': datetime.utcnow(),
            'last_login': None,
            'is_active': True
        }
        return self.collection.insert_one(admin)

    def find_by_login(self, identifier):
        return self.collection.find_one({
            '$or': [
                {'mobile': identifier},
                {'employee_id': identifier}
            ]
        })

    def update_last_login(self, admin_id):
        from bson import ObjectId
        self.collection.update_one(
            {'_id': ObjectId(admin_id)},
            {'$set': {'last_login': datetime.utcnow()}}
        )

    def verify_password(self, plain, hashed):
        return bcrypt.checkpw(plain.encode(), hashed)
