import json
import time
from typing import Optional, Any

from flask import Blueprint, Flask, jsonify, make_response, render_template, request
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt, current_user
from werkzeug.exceptions import NotFound
from dto.user import UserProfile

usersRoute = Blueprint("users", __name__)

with open("{}/databases/users.json".format("."), "r") as jsf:
    users = json.load(jsf)["users"]


def find_user_by_id(user_id) -> Optional[Any]:
    for u in users:
        if str(user_id) == u["id"]:
            return u

def userNoPassword(user: Optional[Any]) -> Optional[Any]:
    if "password" in user:
        user.pop("password",None)
    return user


@usersRoute.route("/users", methods=["GET"])
@jwt_required()
def getUsers():
    claims = get_jwt()
    role = claims.get("role")

    if role != "ADMIN":
        return make_response(jsonify({"error": "forbidden"}), 403)

    return make_response(jsonify(userNoPassword(users)), 200)



@usersRoute.route("/users/me", methods=["GET"])
@jwt_required()
def getUser():
    identity = get_jwt_identity()

    user = find_user_by_id(identity)

    if not user:
        return make_response(jsonify({"error": "User not found"}), 404)

    return make_response(jsonify(userNoPassword(user)), 200)


@usersRoute.route("/users/<user_id>", methods=["GET"])
@jwt_required()
def getUserById(user_id):

    claims = get_jwt()
    role = claims.get("role")
    if role != "ADMIN":
        return make_response(jsonify({"error": "forbidden"}), 403)

    user = find_user_by_id(user_id)

    if not user:
        return make_response(jsonify({"error": "User not found"}), 404)

    return make_response(jsonify(userNoPassword(user)), 200)


@usersRoute.route("/users/<user_id>", methods=["PUT"])
@jwt_required()
def updateUser(user_id):
    data = request.get_json()
    user = find_user_by_id(user_id)
    if not user:
        return make_response(jsonify({"error": "User not found"}), 404)

    if current_user["role"] != "ADMIN" and current_user["id"] != user_id:
        return make_response(jsonify({"error": "Unauthorized to update this user"}), 403)

    if "email" in data:
        user["email"] = data["email"]

    if "name" in data:
        user["name"] = data["name"]

    # Only let admins modify roles
    if "role" in data and current_user["role"] == "ADMIN":
        user["role"] = data["role"]

    # Automatically refresh their last active timestamp
    user["last_active"] = int(time.time())

    return make_response(jsonify(userNoPassword(user)), 200)


@usersRoute.route("/users/<user_id>", methods=["DELETE"])
@jwt_required()
def deleteUser(user_id):
    user = find_user_by_id(user_id)

    if not user:
        return make_response(jsonify({"error": "User not found"}), 404)

    if current_user["role"] != "ADMIN" and current_user["id"] != user_id:
        return make_response(jsonify({"error": "Unauthorized to delete this user"}), 403)

    users.remove(user)
    return make_response(jsonify({"message": "user deleted"}), 200)