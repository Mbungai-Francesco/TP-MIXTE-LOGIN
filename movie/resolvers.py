import requests
from flask_jwt_extended import get_jwt
from graphql import GraphQLError

from config import Config
from db import movies, actors

# a movie uses its UUID as Mongo _id (exposed as `id` in GraphQL)
# never return the Mongo _id of the actors
NO_ID = {"_id": 0}
TIMEOUT = 10


def is_admin():
    return get_jwt().get("role") == "ADMIN"

def check_admin():
    if not is_admin():
        raise GraphQLError("forbidden: ADMIN role required")

def check_rate(rate):
    if not 0 <= rate <= 10:
        raise GraphQLError("invalid rate: between 0 and 10")

def check_text(field, value, max_length=200):
    if not 0 < len(value.strip()) <= max_length:
        raise GraphQLError("invalid %s: 1 to %d characters" % (field, max_length))

def visible(filters):
    # DELETED movies are only visible to admins
    if not is_admin():
        filters["status"] = "AVAILABLE"
    return filters

def cancel_schedules(info, movie_id):
    # ask the Schedule service (REST) to cancel the schedules of the movie, forwarding the caller's token
    token = info.context["request"].headers.get("Authorization")
    try:
        res = requests.put(
            "%s/schedules/movies/%s/cancel" % (Config.SCHEDULE_URL, movie_id),
            headers={"Authorization": token},
            timeout=TIMEOUT,
        )
        res.raise_for_status()
    except requests.RequestException:
        raise GraphQLError("Schedule service unavailable: the movie was not deleted")


# queries
def movie_with_id(_, info, _id):
    return movies.find_one(visible({"_id": _id}))

def movie_with_title(_, info, _title):
    return movies.find_one(visible({"title": _title}))

def all_movies(_, info):
    return list(movies.find(visible({})))

def actor_with_id(_, info, _id):
    # one row per film of the actor
    return list(actors.find({"id": _id}, NO_ID))


# mutations (ADMIN only)
def add_movie(_, info, _id, _title, _director, _rate):
    check_admin()
    check_text("id", _id, 64)
    check_text("title", _title)
    check_text("director", _director)
    check_rate(_rate)
    if movies.find_one({"_id": _id}):
        raise GraphQLError("movie already exists: %s" % _id)
    movie = {"_id": _id, "title": _title.strip(), "director": _director.strip(), "rating": _rate, "status": "AVAILABLE"}
    movies.insert_one(movie)
    return movies.find_one({"_id": _id})

def update_movie_rate(_, info, _id, _rate):
    check_admin()
    check_rate(_rate)
    movie = movies.find_one({"_id": _id})
    if not movie:
        return None
    if movie["status"] == "DELETED":
        raise GraphQLError("movie is deleted: %s" % _id)
    movies.update_one({"_id": _id}, {"$set": {"rating": _rate}})
    return movies.find_one({"_id": _id})

def delete_movie(_, info, _id):
    # soft delete: the movie (and its actors) stay in the database with the DELETED status
    check_admin()
    if not movies.find_one({"_id": _id}):
        return None
    # cancel the schedules first: if Schedule is down, nothing is changed
    cancel_schedules(info, _id)
    movies.update_one({"_id": _id}, {"$set": {"status": "DELETED"}})
    return movies.find_one({"_id": _id})


# fields of Movie
def resolve_movie_id(movie, info):
    return movie["_id"]

def resolve_actors_in_movie(movie, info):
    return list(actors.find({"film": movie["_id"]}, NO_ID))
