import json
from pathlib import Path

from pymongo import MongoClient

from config import Config

SEED_PATH = Path(__file__).resolve().parent / "data" / "times.json"

client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
schedules = client[Config.MONGO_DB]["schedules"]


# a schedule uses its UUID as Mongo _id, returned as `id` by the API
def as_document(schedule):
    doc = {k: v for k, v in schedule.items() if k not in ("_id", "id")}
    doc["_id"] = schedule["id"]
    return doc

def as_json(doc):
    if doc is None:
        return None
    schedule = {k: v for k, v in doc.items() if k != "_id"}
    schedule["id"] = doc["_id"]
    return schedule

def init_db():
    # a movie is shown at most once per date; DELETED schedules do not count
    schedules.create_index([("date", 1), ("movie_id", 1)], unique=True, name="one_movie_per_date",
                           partialFilterExpression={"status": {"$in": ["DRAFT", "AVAILABLE", "CANCELED"]}})
    # first start: fill the collection with the JSON seed
    if schedules.count_documents({}) == 0:
        with open(SEED_PATH, "r") as jsf:
            schedules.insert_many([as_document(s) for s in json.load(jsf)["schedule"]])
        print("schedules collection seeded from %s" % SEED_PATH.name)

def find_schedule(scheduleid):
    return as_json(schedules.find_one({"_id": scheduleid}))
