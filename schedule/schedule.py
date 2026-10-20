import uuid
from datetime import datetime

import requests
from flask import Flask, request, jsonify, make_response
from flask_jwt_extended import JWTManager, jwt_required, get_jwt

from config import Config
from db import schedules, init_db, as_document, as_json, find_schedule

app = Flask(__name__)
app.config.from_object(Config)

# tokens are issued by the User service; the role is read from the token itself
jwt = JWTManager(app)

PORT = 3003
HOST = '0.0.0.0'
TIMEOUT = 10

# statuses an admin can set; DELETED is only set by DELETE /schedules/<id>
STATUSES = ("DRAFT", "AVAILABLE", "CANCELED")
# statuses only visible to admins
HIDDEN = ("DRAFT", "DELETED")


# helpers
def error(message, code):
    return make_response(jsonify({"error": message}), code)

def is_admin():
    return get_jwt().get("role") == "ADMIN"

def is_valid_date(date):
    try:
        datetime.strptime(str(date), "%Y%m%d")
        return len(str(date)) == 8
    except ValueError:
        return False

def ask_movie(query, variables=None):
    # send a GraphQL query to the Movie service, forwarding the caller's token
    res = requests.post(
        Config.MOVIE_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": request.headers.get("Authorization")},
        timeout=TIMEOUT,
    )
    res.raise_for_status()
    return res.json()["data"]

def movie_exists(movie_id):
    # a DELETED movie cannot be scheduled
    query = 'query($id: String!) { movie_with_id(_id: $id) { id status } }'
    movie = ask_movie(query, {"id": movie_id})["movie_with_id"]
    return movie is not None and movie["status"] == "AVAILABLE"

def with_movie_details(schedule_list):
    # one call for all the movies, then each schedule gets its movie
    # (null if it does not exist, or is DELETED and the caller is not an admin)
    query = '{ all_movies { id title director rating status } }'
    movies = {m["id"]: m for m in ask_movie(query)["all_movies"]}
    return [{**s, "movie": movies.get(s["movie_id"])} for s in schedule_list]

def cancel_bookings(schedule_ids):
    # Schedule -> Booking (GraphQL): the bookings of canceled/deleted schedules become CANCELED
    if not schedule_ids:
        return
    query = 'mutation($ids: [String!]!) { cancel_schedules_bookings(_schedule_ids: $ids) }'
    res = requests.post(
        Config.BOOKING_URL,
        json={"query": query, "variables": {"ids": schedule_ids}},
        headers={"Authorization": request.headers.get("Authorization")},
        timeout=TIMEOUT,
    )
    res.raise_for_status()
    if res.json().get("errors"):
        raise requests.RequestException(res.json()["errors"][0]["message"])

def visible_schedules():
    # optional filters: ?date=20151201&movie_id=...&status=AVAILABLE
    filters = {}
    for field in ("date", "movie_id", "status"):
        if request.args.get(field):
            filters[field] = request.args.get(field)

    # DRAFT and DELETED schedules are only visible to admins
    if not is_admin():
        if filters.get("status") in HIDDEN:
            return None
        filters.setdefault("status", {"$nin": list(HIDDEN)})

    return [as_json(doc) for doc in schedules.find(filters).sort([("date", 1), ("movie_id", 1)])]


# JWT errors with the same JSON format as the rest of the API
@jwt.unauthorized_loader
def missing_token_callback(reason):
    return error("token is missing or invalid", 401)

@jwt.invalid_token_loader
def invalid_token_callback(reason):
    return error("token is missing or invalid", 401)

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return error("token has expired", 401)


# root message
@app.route("/", methods=['GET'])
def home():
    return make_response("<h1 style='color:blue'>Welcome to the Showtime service!</h1>", 200)


@app.route("/schedules", methods=['GET'])
@jwt_required()
def get_schedules():
    result = visible_schedules()
    if result is None:
        return error("forbidden", 403)
    return make_response(jsonify(result), 200)


# Schedule -> Movie: same list, each schedule with the details of its movie
@app.route("/schedules/details", methods=['GET'])
@jwt_required()
def get_schedules_details():
    result = visible_schedules()
    if result is None:
        return error("forbidden", 403)
    try:
        return make_response(jsonify(with_movie_details(result)), 200)
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return error("Movie service unavailable", 502)


@app.route("/schedules/<scheduleid>", methods=['GET'])
@jwt_required()
def get_schedule(scheduleid):
    schedule = find_schedule(scheduleid)
    if not schedule or (schedule["status"] in HIDDEN and not is_admin()):
        return error("schedule not found", 404)
    return make_response(jsonify(schedule), 200)


@app.route("/schedules/<scheduleid>/details", methods=['GET'])
@jwt_required()
def get_schedule_details(scheduleid):
    schedule = find_schedule(scheduleid)
    if not schedule or (schedule["status"] in HIDDEN and not is_admin()):
        return error("schedule not found", 404)
    try:
        return make_response(jsonify(with_movie_details([schedule])[0]), 200)
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return error("Movie service unavailable", 502)


@app.route("/schedules", methods=['POST'])
@jwt_required()
def create_schedule():
    if not is_admin():
        return error("forbidden", 403)

    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        req = {}
    for field in ("date", "movie_id"):
        if req.get(field) in (None, ""):
            return error(f"missing field: {field}", 400)
        # strings only: an object like {"$ne": null} would become a Mongo operator
        if not isinstance(req[field], str):
            return error(f"invalid {field}: a string is expected", 400)
    if not is_valid_date(req["date"]):
        return error("invalid date: expected YYYYMMDD", 400)

    status = req.get("status", "DRAFT")
    if not isinstance(status, str) or status not in STATUSES:
        return error(f"invalid status: {status}", 400)

    # a DELETED schedule frees its slot: the same movie can be scheduled again on that date
    if schedules.find_one({"date": req["date"], "movie_id": req["movie_id"], "status": {"$ne": "DELETED"}}):
        return error("this movie is already scheduled on this date", 409)

    try:
        if not movie_exists(req["movie_id"]):
            return error(f"unknown movie: {req['movie_id']}", 422)
    except (requests.RequestException, KeyError, ValueError):
        return error("Movie service unavailable", 502)

    schedule = {
        "id": str(uuid.uuid4()),
        "date": req["date"],
        "movie_id": req["movie_id"],
        "status": status,
    }
    schedules.insert_one(as_document(schedule))
    return make_response(jsonify(find_schedule(schedule["id"])), 201)


@app.route("/schedules/<scheduleid>/<status>", methods=['PUT'])
@jwt_required()
def update_schedule_status(scheduleid, status):
    if not is_admin():
        return error("forbidden", 403)
    if status not in STATUSES:
        return error(f"invalid status: {status}", 400)

    schedule = find_schedule(scheduleid)
    if not schedule:
        return error("schedule not found", 404)
    if schedule["status"] == "DELETED":
        return error("schedule is deleted", 409)
    # a canceled schedule is final
    if schedule["status"] == "CANCELED" and status != "CANCELED":
        return error("a canceled schedule cannot be reopened", 409)

    # cancel the bookings first: if Booking is down, nothing is changed
    if status == "CANCELED" and schedule["status"] != "CANCELED":
        try:
            cancel_bookings([scheduleid])
        except (requests.RequestException, ValueError):
            return error("Booking service unavailable", 502)

    schedules.update_one({"_id": scheduleid}, {"$set": {"status": status}})
    return make_response(jsonify(find_schedule(scheduleid)), 200)


# called by the Movie service before a movie is deleted
@app.route("/schedules/movies/<movieid>/cancel", methods=['PUT'])
@jwt_required()
def cancel_movie_schedules(movieid):
    if not is_admin():
        return error("forbidden", 403)
    filters = {"movie_id": movieid, "status": {"$nin": ["CANCELED", "DELETED"]}}
    try:
        cancel_bookings([doc["_id"] for doc in schedules.find(filters, {"_id": 1})])
    except (requests.RequestException, ValueError):
        return error("Booking service unavailable", 502)
    result = schedules.update_many(filters, {"$set": {"status": "CANCELED"}})
    return make_response(jsonify({"movie_id": movieid, "canceled": result.modified_count}), 200)


@app.route("/schedules/<scheduleid>", methods=['DELETE'])
@jwt_required()
def delete_schedule(scheduleid):
    if not is_admin():
        return error("forbidden", 403)
    # an already deleted schedule is not found
    schedule = find_schedule(scheduleid)
    if not schedule or schedule["status"] == "DELETED":
        return error("schedule not found", 404)
    # cancel the bookings first: if Booking is down, nothing is changed
    try:
        cancel_bookings([scheduleid])
    except (requests.RequestException, ValueError):
        return error("Booking service unavailable", 502)
    # soft delete: the schedule stays in the database with the DELETED status
    schedules.update_one({"_id": scheduleid}, {"$set": {"status": "DELETED"}})
    return make_response(jsonify({"message": "schedule deleted"}), 200)


if __name__ == "__main__":
    init_db()
    print("Server running in port %s" % (PORT))
    app.run(host=HOST, port=PORT)
