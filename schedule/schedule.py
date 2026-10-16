import json

from config import Config
from flask import Flask, jsonify, make_response, render_template, request
from flask_jwt_extended import JWTManager
import requests
from werkzeug.exceptions import NotFound

app = Flask(__name__)

app.config.from_object(Config)

jwt = JWTManager(app)

PORT = 3003
HOST = '0.0.0.0'
USER_PORT = 3004
TIMEOUT = 90

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    user_id = jwt_data["sub"]
    token = request.headers.get("Authorization")

    headers = {
        "Authorization": token,
        "Accept": "application/json",
    }

    url = f"http://{HOST}:{USER_PORT}/users/{user_id}"
    res = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT,
    )

    res.raise_for_status()

    user = res.json()

    return user

with open('{}/databases/times.json'.format("."), "r") as jsf:
   schedule = json.load(jsf)["schedule"]

@app.route("/", methods=['GET'])
def home():
   return "<h1 style='color:blue'>Welcome to the Showtime service!</h1>"

if __name__ == "__main__":
   print("Server running in port %s"%(PORT))
   app.run(host=HOST, port=PORT)
