import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/Beacon")
    DB_NAME = "beacon"
    SECRET_KEY = os.getenv("SECRET_KEY")
    
    JWT_SECRET = os.getenv("JWT_SECRET", "jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    BCRYPT_ROUNDS = 12