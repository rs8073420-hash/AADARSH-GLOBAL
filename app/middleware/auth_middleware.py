from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get('role') != 'admin':
                return jsonify({'error': 'Admin access required'}), 403
        except Exception as e:
            return jsonify({'error': 'Authentication required', 'details': str(e)}), 401
        return f(*args, **kwargs)
    return decorated

def employee_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get('role') not in ['employee', 'admin']:
                return jsonify({'error': 'Employee access required'}), 403
        except Exception as e:
            return jsonify({'error': 'Authentication required', 'details': str(e)}), 401
        return f(*args, **kwargs)
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception as e:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated
