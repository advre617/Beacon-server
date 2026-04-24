from datetime import datetime
from extensions.mongodb import get_db
from bson.objectid import ObjectId

class User:
    @staticmethod
    def create_user(email: str, username: str, password_hash: str):
        db = get_db()
        user = {
            "email": email.lower(),
            "username": username,
            "password_hash": password_hash,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_login": None
        }
        result = db.users.insert_one(user)
        return str(result.inserted_id)
    
    @staticmethod
    def find_by_email(email: str):
        db = get_db()
        return db.users.find_one({"email": email.lower()})
    
    @staticmethod
    def find_by_id(user_id: str):
        db = get_db()
        try:
            return db.users.find_one({"_id": ObjectId(user_id)})
        except:
            return None
    
    @staticmethod
    def update_last_login(user_id: str):
        db = get_db()
        db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_login": datetime.utcnow()}}
        )
    
    @staticmethod
    def to_dict(user):
        if not user:
            return None
        return {
            "id": str(user["_id"]),
            "email": user["email"],
            "username": user["username"],
            "is_active": user.get("is_active", True),
            "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
            "last_login": user["last_login"].isoformat() if user.get("last_login") else None
        }