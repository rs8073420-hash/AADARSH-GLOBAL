import requests
from pymongo import MongoClient

# Get employee token
client = MongoClient("mongodb://localhost:27017/")
db = client.richa_global

# get a real employee
emp = db.employees.find_one()
if not emp:
    print("No employee found!")
else:
    # use login api
    r = requests.post("http://localhost:5000/api/auth/login", json={"identifier": emp["email"], "password": "password123", "role": "employee"})
    print("Login:", r.status_code, r.text)
    if r.status_code == 200:
        token = r.json().get('access_token')
        
        # Test checkin with remarks
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        print("CHECKIN 1 (With remarks)")
        r = requests.post("http://localhost:5000/api/attendance/check-in", headers=headers, json={"remarks": "Sorry I am late"})
        print("Checkin response:", r.status_code)
        try:
            print(r.json())
        except:
            print(r.text[:500])
