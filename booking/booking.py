import json
from typing import Optional, Any
import requests

from ariadne import graphql_sync, make_executable_schema, load_schema_from_path, ObjectType, QueryType, MutationType
from flask import Flask, request, jsonify, make_response
from config import Config
from flask_jwt_extended import JWTManager


PORT = 3002
HOST = '0.0.0.0'
USER_PORT = 3004
TIMEOUT = 90
app = Flask(__name__)

app.config.from_object(Config)

jwt = JWTManager(app)

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

# todo create elements for Ariadne
type_defs = load_schema_from_path("booking.graphql")
query = QueryType()
mutation = MutationType()
schema = make_executable_schema(type_defs, query, mutation)


# root message
@app.route("/", methods=['GET'])
def home():
    return make_response("<h1 style='color:blue'>Welcome to the Booking service!</h1>",200)

# graphql entry points
@app.route('/graphql', methods=['POST'])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value=None, debug=app.debug)
    status_code = 200 if success else 400
    return jsonify(result), status_code

if __name__ == "__main__":
    print("Server running in port %s"%(PORT))
    app.run(host=HOST, port=PORT)