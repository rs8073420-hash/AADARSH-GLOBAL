from ..models.employee import EmployeeModel
from ..models.admin import AdminModel
import bcrypt

class AuthService:
    def login(self, identifier, password):
        # Try admin first
        admin_model = AdminModel()
        user = admin_model.find_by_login(identifier)
        if user:
            if not user.get('is_active', True):
                return 'inactive', None
            if bcrypt.checkpw(password.encode(), user['password']):
                admin_model.update_last_login(str(user['_id']))
                return user, 'admin'
            return None, None

        # Try employee
        emp_model = EmployeeModel()
        user = emp_model.find_by_login(identifier)
        if user:
            if not user.get('is_active', True):
                return 'inactive', None
            if bcrypt.checkpw(password.encode(), user['password']):
                emp_model.set_online(str(user['_id']), True)
                return user, 'employee'

        return None, None

    def logout(self, identity, role):
        if role == 'employee':
            emp_model = EmployeeModel()
            from bson import ObjectId
            from ..extensions import get_db
            db = get_db()
            db.employees.update_one(
                {'_id': ObjectId(identity)},
                {'$set': {'is_online': False}}
            )
