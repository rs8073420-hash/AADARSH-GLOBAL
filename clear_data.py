from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/richa_global"
client = MongoClient(MONGO_URI)
db = client.get_default_database()

# Delete all data in specific collections
db.employees.delete_many({})
db.tasks.delete_many({})
db.attendance.delete_many({})
db.messages.delete_many({})

print("All employee, task, attendance, and message data has been deleted successfully!")
