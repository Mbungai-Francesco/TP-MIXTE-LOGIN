import json
from pathlib import Path

from pymongo import MongoClient

from config import Config

SEED_PATH = Path(__file__).resolve().parent / "data" / "bookings.json"

client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
bookings = client[Config.MONGO_DB]["bookings"]


def init_db():
    # a booking is identified by (userid, schedule_id)
    bookings.create_index([("userid", 1), ("schedule_id", 1)], unique=True)
    # first start: fill the collection with the JSON seed
    if bookings.count_documents({}) == 0:
        with open(SEED_PATH, "r") as jsf:
            bookings.insert_many(json.load(jsf)["bookings"])
        print("bookings collection seeded from %s" % SEED_PATH.name)
