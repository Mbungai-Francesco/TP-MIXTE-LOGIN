from ariadne import graphql_sync, make_executable_schema, load_schema_from_path, ObjectType, QueryType, MutationType
from flask import Flask, request, jsonify, make_response
from flask_jwt_extended import JWTManager, jwt_required

import resolvers as r
from config import Config
from db import init_db

PORT = 3002
HOST = '0.0.0.0'
app = Flask(__name__)

app.config.from_object(Config)

# tokens are issued by the User service; the role is read from the token itself
jwt = JWTManager(app)

def error(message, code):
    return make_response(jsonify({"error": message}), code)

@jwt.unauthorized_loader
def missing_token_callback(reason):
    return error("token is missing or invalid", 401)

@jwt.invalid_token_loader
def invalid_token_callback(reason):
    return error("token is missing or invalid", 401)

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return error("token has expired", 401)

# elements for Ariadne
type_defs = load_schema_from_path("booking.graphql")
query = QueryType()
mutation = MutationType()
booking = ObjectType('Booking')
schedule = ObjectType('Schedule')

query.set_field('my_bookings', r.my_bookings)
query.set_field('bookings_for_user', r.bookings_for_user)
query.set_field('all_bookings', r.all_bookings)
query.set_field('bookings_for_schedule', r.bookings_for_schedule)
query.set_field('bookings_for_movie', r.bookings_for_movie)

mutation.set_field('add_booking', r.add_booking)
mutation.set_field('cancel_booking', r.cancel_booking)
mutation.set_field('cancel_schedules_bookings', r.cancel_schedules_bookings)
mutation.set_field('cancel_user_bookings', r.cancel_user_bookings)

booking.set_field('schedule', r.resolve_schedule_in_booking)
schedule.set_field('movie', r.resolve_movie_in_schedule)

schema = make_executable_schema(type_defs, query, mutation, booking, schedule)


# root message
@app.route("/", methods=['GET'])
def home():
    return make_response("<h1 style='color:blue'>Welcome to the Booking service!</h1>",200)

# graphql entry points
@app.route('/graphql', methods=['POST'])
@jwt_required()
def graphql_server():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("the body must be a JSON object: {\"query\": \"...\"}", 400)
    success, result = graphql_sync(
        schema,
        data,
        context_value={"request": request},
        debug=app.debug
    )
    status_code = 200 if success else 400
    return jsonify(result), status_code

if __name__ == "__main__":
    init_db()
    print("Server running in port %s"%(PORT))
    app.run(host=HOST, port=PORT)
