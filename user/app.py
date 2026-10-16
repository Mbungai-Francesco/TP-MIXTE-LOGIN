import json
from typing import Optional, Any

from config import Config
from flask import Flask, jsonify, make_response, render_template, request
from flask_jwt_extended import JWTManager
from routes.auth import auth
from routes.user import usersRoute
from werkzeug.exceptions import NotFound

app = Flask(__name__)

app.config.from_object(Config)

jwt = JWTManager(app)

with open("{}/databases/users.json".format("."), "r") as jsf:
   users = json.load(jsf)["users"]


def find_user_by_id(user_id) -> Optional[Any]:
   for u in users:
      if str(user_id) == u["id"]:
         return u

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
   user_id = jwt_data["sub"]

   user = find_user_by_id(user_id)

   return user


app.register_blueprint(auth)
app.register_blueprint(usersRoute)

PORT = 3004
HOST = '0.0.0.0'

@app.route("/", methods=['GET'])
def home():
   return "<h1 style='color:blue'>Welcome to the User service!</h1>"


if __name__ == "__main__":
   print(f"Server running in port {PORT}")
   app.run(host=HOST, port=PORT)
