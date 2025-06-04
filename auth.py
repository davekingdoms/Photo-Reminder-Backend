import datetime, bcrypt, jwt
from flask import Blueprint, request, jsonify, current_app

auth_bp = Blueprint("auth", __name__)

def _users():
    """Restituisce la collection MongoDB degli utenti"""
    return current_app.config["USERS_COLL"]


def _jwt_for(username: str) -> str:
    """
    Genera un JWT HS256 con:
      • sub = <username>
      • exp = +30 giorni
    """
    token = jwt.encode(
        {
            "sub": username,
            "exp": datetime.datetime.now(datetime.timezone.utc)
                   + datetime.timedelta(days=30),
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )
 
    return token if isinstance(token, str) else token.decode("utf-8")


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400
    if _users().find_one({"username": username}):
        return jsonify({"message": "User already exists"}), 400

    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    _users().insert_one(
        {
            "username":   username,
            "password":   hashed_pw,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
    )

    return jsonify(
        {
            "message": "User registered successfully",
            "token":   _jwt_for(username),
        }
    ), 201


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    user = _users().find_one({"username": username})
    if not user or not bcrypt.checkpw(password.encode(), user["password"]):
        return jsonify({"message": "Invalid username or password"}), 401

    return jsonify(
        {
            "token":    _jwt_for(username),
            "username": username,     
        }
    ), 200
