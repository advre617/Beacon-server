from pymongo import MongoClient

mongo_client = None

def init_mongo(app):
    global mongo_client
    mongo_client = MongoClient(app.config["MONGO_URI"])
    return mongo_client[app.config["DB_NAME"]]

def get_db():
    return mongo_client.get_database()