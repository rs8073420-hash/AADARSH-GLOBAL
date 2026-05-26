from datetime import datetime
from ..extensions import get_db
import bcrypt
from bson import ObjectId

class EmployeeModel:
    def __init__(self):
        self.collection = get_db().employees

    def create(self, data):
        hashed = bcrypt.hashpw(data['password'].encode(), bcrypt.gensalt())
        employee = {
            'name': data['name'],
            'email': data.get('email', ''),
            'mobile': data['mobile'],
            'employee_id': data['employee_id'],
            'password': hashed,
            'role': 'employee',
            'department': data.get('department', ''),
            'designation': data.get('designation', ''),
            'avatar': data.get('avatar', ''),
            'is_active': True,
            'is_online': False,
            'created_at': datetime.utcnow(),
            'last_login': None,
            'address': data.get('address', ''),
            'join_date': data.get('join_date', datetime.utcnow().strftime('%Y-%m-%d'))
        }
        return self.collection.insert_one(employee)

    def find_by_login(self, identifier):
        return self.collection.find_one({
            '$or': [
                {'mobile': identifier},
                {'employee_id': identifier}
            ]
        })

    def find_by_id(self, emp_id):
        return self.collection.find_one({'_id': ObjectId(emp_id)})

    def find_by_employee_id(self, employee_id):
        return self.collection.find_one({'employee_id': employee_id})

    def get_all(self, filters={}):
        return list(self.collection.find(filters))

    def update(self, emp_id, data):
        if 'password' in data and data['password']:
            data['password'] = bcrypt.hashpw(data['password'].encode(), bcrypt.gensalt())
        data['updated_at'] = datetime.utcnow()
        return self.collection.update_one({'_id': ObjectId(emp_id)}, {'$set': data})

    def delete(self, emp_id):
        return self.collection.delete_one({'_id': ObjectId(emp_id)})

    def toggle_active(self, emp_id, status):
        return self.collection.update_one(
            {'_id': ObjectId(emp_id)},
            {'$set': {'is_active': status}}
        )

    def set_online(self, emp_id, status):
        return self.collection.update_one(
            {'_id': ObjectId(emp_id)},
            {'$set': {'is_online': status, 'last_login': datetime.utcnow()}}
        )

    def set_offline(self, emp_id):
        return self.collection.update_one(
            {'_id': ObjectId(emp_id)},
            {'$set': {'is_online': False}}
        )

    def verify_password(self, plain, hashed):
        return bcrypt.checkpw(plain.encode(), hashed)

    def count(self, filters={}):
        return self.collection.count_documents(filters)
