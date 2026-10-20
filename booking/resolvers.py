import requests
from flask_jwt_extended import get_jwt, get_jwt_identity
from graphql import GraphQLError

from config import Config
from db import bookings

# never return the Mongo _id: a booking is identified by (userid, schedule_id)
NO_ID = {"_id": 0}
TIMEOUT = 10


def is_admin():
    return get_jwt().get("role") == "ADMIN"

def check_admin():
    if not is_admin():
        raise GraphQLError("forbidden: ADMIN role required")

def owner_or_admin(userid):
    # without userid, the caller works on their own bookings
    me = get_jwt_identity()
    userid = userid or me
    if userid != me and not is_admin():
        raise GraphQLError("forbidden: not your bookings")
    return userid

def token(info):
    # the caller's token is forwarded to the other services
    return {"Authorization": info.context["request"].headers.get("Authorization")}


# calls to the other services
def get_schedule(info, schedule_id):
    # Booking -> Schedule (REST)
    try:
        res = requests.get("%s/schedules/%s" % (Config.SCHEDULE_URL, schedule_id), headers=token(info), timeout=TIMEOUT)
    except requests.RequestException:
        raise GraphQLError("Schedule service unavailable")
    if res.status_code == 404:
        return None
    if not res.ok:
        raise GraphQLError("Schedule service unavailable")
    return res.json()

def user_is_active(info, userid):
    # Booking -> User (REST): the account must exist and not be DELETED
    try:
        res = requests.get("%s/users/%s" % (Config.USER_URL, userid), headers=token(info), timeout=TIMEOUT)
    except requests.RequestException:
        raise GraphQLError("User service unavailable")
    # 401: the caller's own account has been deleted
    if res.status_code in (401, 404):
        return False
    if not res.ok:
        raise GraphQLError("User service unavailable")
    return res.json().get("status") == "ACTIVE"

def all_schedules(info):
    # Booking -> Schedule (REST), one call per GraphQL request
    if "schedules" not in info.context:
        try:
            res = requests.get("%s/schedules" % Config.SCHEDULE_URL, headers=token(info), timeout=TIMEOUT)
            res.raise_for_status()
        except requests.RequestException:
            raise GraphQLError("Schedule service unavailable")
        info.context["schedules"] = {s["id"]: s for s in res.json()}
    return info.context["schedules"]

def all_movies(info):
    # Booking -> Movie (GraphQL), one call per GraphQL request
    if "movies" not in info.context:
        query = '{ all_movies { id title director rating status } }'
        try:
            res = requests.post(Config.MOVIE_URL, json={"query": query}, headers=token(info), timeout=TIMEOUT)
            res.raise_for_status()
            movies = res.json()["data"]["all_movies"]
        except (requests.RequestException, KeyError, TypeError, ValueError):
            raise GraphQLError("Movie service unavailable")
        info.context["movies"] = {m["id"]: m for m in movies}
    return info.context["movies"]


# queries
def my_bookings(_, info):
    return list(bookings.find({"userid": get_jwt_identity()}, NO_ID))

def bookings_for_user(_, info, _userid):
    return list(bookings.find({"userid": owner_or_admin(_userid)}, NO_ID))

def all_bookings(_, info):
    check_admin()
    return list(bookings.find({}, NO_ID))

def bookings_for_schedule(_, info, _schedule_id):
    check_admin()
    return list(bookings.find({"schedule_id": _schedule_id}, NO_ID))

def bookings_for_movie(_, info, _movie_id):
    # Booking -> Schedule (REST): the schedules of the movie, then their bookings
    check_admin()
    try:
        res = requests.get("%s/schedules" % Config.SCHEDULE_URL, params={"movie_id": _movie_id}, headers=token(info), timeout=TIMEOUT)
        res.raise_for_status()
    except requests.RequestException:
        raise GraphQLError("Schedule service unavailable")
    schedule_ids = [s["id"] for s in res.json()]
    return list(bookings.find({"schedule_id": {"$in": schedule_ids}}, NO_ID))


# mutations
def add_booking(_, info, _schedule_id, _userid=None):
    userid = owner_or_admin(_userid)
    # checked even for the caller: the token of a deleted account is still signed and not expired
    if not user_is_active(info, userid):
        raise GraphQLError("user not found: %s" % userid)

    schedule = get_schedule(info, _schedule_id)
    if not schedule:
        raise GraphQLError("schedule not found: %s" % _schedule_id)
    if schedule["status"] != "AVAILABLE":
        raise GraphQLError("schedule is not open for booking: %s" % schedule["status"])

    key = {"userid": userid, "schedule_id": _schedule_id}
    booking = bookings.find_one(key, NO_ID)
    if booking and booking["status"] == "CONFIRMED":
        raise GraphQLError("booking already exists")
    # a canceled booking is confirmed again, otherwise a new one is created
    bookings.update_one(key, {"$set": {"status": "CONFIRMED"}}, upsert=True)
    return bookings.find_one(key, NO_ID)

def cancel_booking(_, info, _schedule_id, _userid=None):
    key = {"userid": owner_or_admin(_userid), "schedule_id": _schedule_id}
    if not bookings.find_one(key):
        raise GraphQLError("booking not found")
    bookings.update_one(key, {"$set": {"status": "CANCELED"}})
    return bookings.find_one(key, NO_ID)

def cancel_schedules_bookings(_, info, _schedule_ids):
    # called by the Schedule service when schedules are canceled or deleted
    check_admin()
    result = bookings.update_many(
        {"schedule_id": {"$in": _schedule_ids}, "status": "CONFIRMED"},
        {"$set": {"status": "CANCELED"}},
    )
    return result.modified_count

def cancel_user_bookings(_, info, _userid):
    # called by the User service when an account is deleted (by its owner or an admin)
    userid = owner_or_admin(_userid)
    result = bookings.update_many(
        {"userid": userid, "status": "CONFIRMED"},
        {"$set": {"status": "CANCELED"}},
    )
    return result.modified_count


# nested fields
def resolve_schedule_in_booking(booking, info):
    return all_schedules(info).get(booking["schedule_id"])

def resolve_movie_in_schedule(schedule, info):
    return all_movies(info).get(schedule["movie_id"])
