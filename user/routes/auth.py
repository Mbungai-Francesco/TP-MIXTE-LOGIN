import json
import random
import string
from datetime import datetime, timezone

from flask import Blueprint, Flask, jsonify, make_response, render_template, request
from flask_jwt_extended import create_access_token, jwt_required
from werkzeug.exceptions import NotFound
from werkzeug.security import check_password_hash, generate_password_hash

auth = Blueprint("auth", __name__)

with open("{}/databases/users.json".format("."), "r") as jsf:
    users = json.load(jsf)["users"]


def find_user_by_email(email):
    for u in users:
        if str(email) == u["email"]:
            return u


def hash_password(password):
    return generate_password_hash(password)


def check_password(password, userPass):
    return check_password_hash(userPass, password)


def generateId():
    chars = string.ascii_uppercase + string.digits
    return "-".join("".join(random.choice(chars) for _ in range(4)) for _ in range(3))


def generateTime():
    # Python Example
    timestamp = 1360031010
    # date = datetime.fromtimestamp(timestamp)
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return date.strftime("%Y-%m-%d %H:%M:%S")


@auth.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    user = find_user_by_email(email)

    if not user or not user["password"] == str(password):
        return jsonify({"error": "Invalid credentials"}), 401

    # if not user or not check_password(password, user["password"]):
    #     return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(
        identity=str(user["id"]), additional_claims={"role": user["role"]}
    )

    return make_response(jsonify({"jwt": token}), 200)


@auth.route("/users", methods=["POST"])
@jwt_required()
def createUser():
    data = request.get_json()

    user = {
        "id": generateId(),
        "email": data.get("email"),
        "password": hash_password(data.get("password")),
        "role": data.get("role"),
        "name": data.get("name"),
        "last_active": generateTime(),
    }

    users.append(user)

    return make_response(jsonify(user), 201)
