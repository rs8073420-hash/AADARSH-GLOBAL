"""
Run this script ONCE to create the first admin user.
Usage: python create_admin.py
"""
from pymongo import MongoClient
import bcrypt
from datetime import datetime

MONGO_URI = "mongodb://localhost:27017/richa_global"

client = MongoClient(MONGO_URI)
db = client.get_default_database()

name = "Super Admin"
mobile = "9999999999"
employee_id = "ADMIN001"
password = "Admin@123"

# Check if already exists
if db.admins.find_one({'employee_id': employee_id}):
    print(f"Admin '{employee_id}' already exists!")
else:
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    db.admins.insert_one({
        'name': name,
        'mobile': mobile,
        'employee_id': employee_id,
        'password': hashed,
        'role': 'admin',
        'email': 'admin@richaglobal.com',
        'avatar': '',
        'is_active': True,
        'created_at': datetime.utcnow(),
        'last_login': None
    })
    print(f"""
✅ Admin created successfully!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Login ID : {employee_id}  OR  {mobile}
Password : {password}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Go to: http://localhost:5000/login
""")
