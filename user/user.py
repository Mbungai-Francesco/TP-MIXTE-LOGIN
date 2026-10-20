import re
import time

import requests
from flask import Flask, request, jsonify, make_response
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from db import users, init_db, find_user, find_active_user, PUBLIC_FIELDS

app = Flask(__name__)
app.config.from_object(Config)
jwt = JWTManager(app)

PORT = 3004
HOST = '0.0.0.0'

ROLES = ("USER", "ADMIN")
ID_PATTERN = re.compile(r"[a-z0-9_]{3,32}")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 128
NAME_MAX_LENGTH = 100
EMAIL_MAX_LENGTH = 254
TIMEOUT = 10


# helpers
def error(message, code):
    return make_response(jsonify({"error": message}), code)

def json_body():
    # only a JSON object is accepted (not a list, a string or invalid JSON)
    req = request.get_json(silent=True)
    return req if isinstance(req, dict) else {}

def invalid_field(field, value):
    # returns the error message, or None when the value is valid
    # every value must be a string: an object like {"$ne": null} would become a Mongo operator
    if not isinstance(value, str):
        return f"invalid {field}: a string is expected"
    if field == "id" and not ID_PATTERN.fullmatch(value):
        return "invalid id: 3 to 32 chars among a-z, 0-9, _"
    if field == "email" and (len(value) > EMAIL_MAX_LENGTH or not EMAIL_PATTERN.fullmatch(value)):
        return "invalid email"
    if field == "name" and not 0 < len(value.strip()) <= NAME_MAX_LENGTH:
        return f"invalid name: 1 to {NAME_MAX_LENGTH} characters"
    if field == "password" and not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH:
        return f"invalid password: {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters"
    if field == "role" and value not in ROLES:
        return f"invalid role: {value}"
    return None

def is_admin():
    return get_jwt().get("role") == "ADMIN"

def is_admin_or_owner(userid):
    return is_admin() or get_jwt_identity() == userid

def cancel_bookings(userid):
    # User -> Booking (GraphQL): the bookings of a deleted user become CANCELED
    query = 'mutation($id: String!) { cancel_user_bookings(_userid: $id) }'
    res = requests.post(
        Config.BOOKING_URL,
        json={"query": query, "variables": {"id": userid}},
        headers={"Authorization": request.headers.get("Authorization")},
        timeout=TIMEOUT,
    )
    res.raise_for_status()
    if res.json().get("errors"):
        raise requests.RequestException(res.json()["errors"][0]["message"])


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

# the token of a deleted account is refused at once, even before it expires
@jwt.token_in_blocklist_loader
def deleted_account_callback(jwt_header, jwt_payload):
    return find_active_user("id", jwt_payload["sub"]) is None

@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return error("this account has been deleted", 401)


# root message
@app.route("/", methods=['GET'])
def home():
    return make_response("<h1 style='color:blue'>Welcome to the User service!</h1>", 200)


@app.route("/login", methods=['POST'])
def login():
    req = json_body()
    email = req.get("email")
    password = req.get("password")
    if not email or not password:
        return error("missing field: email or password", 400)
    # strings only: {"email": {"$ne": null}} must not match any user
    if not isinstance(email, str) or not isinstance(password, str):
        return error("invalid field: email and password must be strings", 400)

    # a deleted account cannot log in
    user = find_active_user("email", email, {"_id": 0})
    if not user or not check_password_hash(user["password"], password):
        return error("Invalid credentials", 401)

    users.update_one({"id": user["id"]}, {"$set": {"last_active": int(time.time())}})

    token = create_access_token(identity=user["id"], additional_claims={"role": user["role"]})
    expires_in = int(app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds())
    return make_response(jsonify({"access_token": token, "token_type": "Bearer", "expires_in": expires_in}), 200)


@app.route("/users", methods=['GET'])
@jwt_required()
def get_users():
    if not is_admin():
        return error("forbidden", 403)
    return make_response(jsonify(list(users.find({}, PUBLIC_FIELDS))), 200)


@app.route("/users", methods=['POST'])
@jwt_required(optional=True)
def create_user():
    req = json_body()
    for field in ("id", "email", "name", "password"):
        if req.get(field) in (None, ""):
            return error(f"missing field: {field}", 400)
        message = invalid_field(field, req[field])
        if message:
            return error(message, 400)

    role = req.get("role", "USER")
    message = invalid_field("role", role)
    if message:
        return error(message, 400)
    # only an authenticated admin can create another admin
    if role == "ADMIN" and not (get_jwt_identity() and is_admin()):
        return error("forbidden", 403)

    if find_user("id", req["id"]) or find_user("email", req["email"]):
        return error("user already exists", 409)

    user = {
        "id": req["id"],
        "email": req["email"],
        "password": generate_password_hash(req["password"]),
        "role": role,
        "name": req["name"].strip(),
        "last_active": int(time.time()),
        "status": "ACTIVE",
    }
    users.insert_one(user)
    return make_response(jsonify(find_user("id", user["id"])), 201)


@app.route("/users/me", methods=['GET'])
@jwt_required()
def get_me():
    user = find_user("id", get_jwt_identity())
    if not user:
        return error("user not found", 404)
    return make_response(jsonify(user), 200)


@app.route("/users/<userid>", methods=['GET'])
@jwt_required()
def get_user(userid):
    # the owner is allowed too; an admin also sees the DELETED accounts (with their status)
    if not is_admin_or_owner(userid):
        return error("forbidden", 403)
    user = find_user("id", userid)
    if not user:
        return error("user not found", 404)
    return make_response(jsonify(user), 200)


@app.route("/users/<userid>", methods=['PUT'])
@jwt_required()
def update_user(userid):
    if not is_admin_or_owner(userid):
        return error("forbidden", 403)

    req = json_body()
    fields = [field for field in ("name", "email", "password", "role") if field in req]
    if not fields:
        return error("nothing to update: name, email, password or role expected", 400)

    user = find_user("id", userid)
    if not user:
        return error("user not found", 404)
    if user["status"] == "DELETED":
        return error("user is deleted", 409)
    if "role" in req and not is_admin():
        return error("forbidden", 403)
    for field in fields:
        message = invalid_field(field, req[field])
        if message:
            return error(message, 400)

    changes = {}
    if "role" in req:
        changes["role"] = req["role"]

    if "email" in req:
        other = find_user("email", req["email"])
        if other and other["id"] != userid:
            return error("email already used", 409)
        changes["email"] = req["email"]

    if "password" in req:
        changes["password"] = generate_password_hash(req["password"])

    if "name" in req:
        changes["name"] = req["name"].strip()

    users.update_one({"id": userid}, {"$set": changes})
    return make_response(jsonify(find_user("id", userid)), 200)


@app.route("/users/<userid>", methods=['DELETE'])
@jwt_required()
def delete_user(userid):
    if not is_admin_or_owner(userid):
        return error("forbidden", 403)

    # an already deleted account is not found
    if not find_active_user("id", userid):
        return error("user not found", 404)
    # cancel the bookings first: if Booking is down, nothing is changed
    try:
        cancel_bookings(userid)
    except (requests.RequestException, ValueError):
        return error("Booking service unavailable", 502)

    # soft delete: the account stays in the database with the DELETED status
    users.update_one({"id": userid}, {"$set": {"status": "DELETED"}})
    return make_response(jsonify({"message": "user deleted"}), 200)


if __name__ == "__main__":
    init_db()
    print("Server running in port %s" % (PORT))
    app.run(host=HOST, port=PORT)
