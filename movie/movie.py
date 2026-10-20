from ariadne import graphql_sync, make_executable_schema, load_schema_from_path, ObjectType, QueryType, MutationType
from flask import Flask, request, jsonify, make_response
from flask_jwt_extended import JWTManager, jwt_required

import resolvers as r
from config import Config
from db import init_db

PORT = 3200
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
type_defs = load_schema_from_path('movie.graphql')
query = QueryType()
mutation = MutationType()
movie = ObjectType('Movie')
actor = ObjectType('Actor')

query.set_field('movie_with_id', r.movie_with_id)
query.set_field('movie_with_title', r.movie_with_title)
query.set_field('all_movies', r.all_movies)
query.set_field('actor_with_id', r.actor_with_id)

mutation.set_field('add_movie', r.add_movie)
mutation.set_field('update_movie_rate', r.update_movie_rate)
mutation.set_field('delete_movie', r.delete_movie)

movie.set_field('id', r.resolve_movie_id)
movie.set_field('actors', r.resolve_actors_in_movie)

schema = make_executable_schema(type_defs, query, mutation, movie, actor)

# root message
@app.route("/", methods=['GET'])
def home():
    return make_response("<h1 style='color:blue'>Welcome to the Movie service!</h1>",200)

# graphql entry points
@app.route('/graphql', methods=['POST'])
# the token is optional: anyone can read the movies, the mutations check the ADMIN role
@jwt_required(optional=True)
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
