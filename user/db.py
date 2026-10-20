import json
from pathlib import Path

from pymongo import MongoClient

from config import Config

SEED_PATH = Path(__file__).resolve().parent / "databases" / "users.json"

# never return the Mongo _id, nor the password
PUBLIC_FIELDS = {"_id": 0, "password": 0}

client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
users = client[Config.MONGO_DB]["users"]


def init_db():
    users.create_index("id", unique=True)
    users.create_index("email", unique=True)
    # first start: fill the collection with the JSON seed
    if users.count_documents({}) == 0:
        with open(SEED_PATH, "r") as jsf:
            users.insert_many(json.load(jsf)["users"])
        print("users collection seeded from %s" % SEED_PATH.name)

def find_user(field, value, projection=PUBLIC_FIELDS):
    # any user, ACTIVE or DELETED (ids and emails stay reserved after a deletion)
    return users.find_one({field: value}, projection)

def find_active_user(field, value, projection=PUBLIC_FIELDS):
    return users.find_one({field: value, "status": "ACTIVE"}, projection)
