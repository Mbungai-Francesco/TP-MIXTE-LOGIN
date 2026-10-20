import json
from pathlib import Path

from pymongo import MongoClient

from config import Config

DATA_DIR = Path(__file__).resolve().parent / "data"

client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[Config.MONGO_DB]
movies = db["movies"]
actors = db["actors"]


def as_movie_document(movie):
    # the movie UUID becomes the Mongo _id
    doc = {k: v for k, v in movie.items() if k not in ("_id", "id")}
    doc["_id"] = movie["id"]
    return doc

def seed(collection, file_name, key, convert=lambda doc: doc):
    # first start: fill the collection with the JSON seed
    if collection.count_documents({}) == 0:
        with open(DATA_DIR / file_name, "r") as jsf:
            collection.insert_many([convert(doc) for doc in json.load(jsf)[key]])
        print("%s collection seeded from %s" % (collection.name, file_name))

def init_db():
    # an actor has one row per film: (id, film) is unique, not id alone
    actors.create_index([("id", 1), ("film", 1)], unique=True)
    seed(movies, "movies.json", "movies", as_movie_document)
    seed(actors, "actors.json", "actors")
