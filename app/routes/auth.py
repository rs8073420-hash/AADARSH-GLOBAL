from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import create_access_token, get_jwt_identity, get_jwt
from ..services.auth_service import AuthService
from ..middleware.auth_middleware import login_required
import json

auth_bp = Blueprint('auth', __name__)
auth_service = AuthService()

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    identifier = data.get('identifier', '').strip()
    password = data.get('password', '').strip()
    
    if not identifier or not password:
        return jsonify({'error': 'Identifier and password are required'}), 400
    
    user, role = auth_service.login(identifier, password)
    
    if user == 'inactive':
        return jsonify({'error': 'Your account is deactivated. Contact admin.'}), 403
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    user_id = str(user['_id'])
    additional_claims = {
        'role': role,
        'name': user.get('name', ''),
        'employee_id': user.get('employee_id', ''),
        'department': user.get('department', '')
    }
    
    access_token = create_access_token(identity=user_id, additional_claims=additional_claims)
    
    user_data = {
        'id': user_id,
        'name': user.get('name', ''),
        'email': user.get('email', ''),
        'mobile': user.get('mobile', ''),
        'employee_id': user.get('employee_id', ''),
        'role': role,
        'department': user.get('department', ''),
        'designation': user.get('designation', ''),
        'avatar': user.get('avatar', '')
    }
    
    return jsonify({
        'access_token': access_token,
        'user': user_data,
        'role': role,
        'message': f'Welcome back, {user.get("name", "")}!'
    }), 200

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    identity = get_jwt_identity()
    claims = get_jwt()
    auth_service.logout(identity, claims.get('role', 'employee'))
    return jsonify({'message': 'Logged out successfully'}), 200

@auth_bp.route('/me', methods=['GET'])
@login_required
def get_me():
    identity = get_jwt_identity()
    claims = get_jwt()
    role = claims.get('role')
    
    from ..extensions import get_db
    from bson import ObjectId
    db = get_db()
    
    if role == 'admin':
        user = db.admins.find_one({'_id': ObjectId(identity)})
    else:
        user = db.employees.find_one({'_id': ObjectId(identity)})
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user['_id'] = str(user['_id'])
    user.pop('password', None)
    user['role'] = role
    
    return jsonify(user), 200

@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    if not old_password or not new_password:
        return jsonify({'error': 'Both passwords required'}), 400
    
    from ..extensions import get_db
    from bson import ObjectId
    import bcrypt
    db = get_db()
    
    role = claims.get('role')
    collection = db.admins if role == 'admin' else db.employees
    user = collection.find_one({'_id': ObjectId(identity)})
    
    if not user or not bcrypt.checkpw(old_password.encode(), user['password']):
        return jsonify({'error': 'Current password is incorrect'}), 400
    
    new_hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
    collection.update_one({'_id': ObjectId(identity)}, {'$set': {'password': new_hashed}})
    
    return jsonify({'message': 'Password changed successfully'}), 200
