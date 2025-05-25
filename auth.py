import datetime, bcrypt, jwt
from flask import Blueprint, request, jsonify, current_app

auth_bp = Blueprint("auth", __name__)

# ─────────────────────────── Helpers ─────────────────────────────── #

def _users():
    """Return the Mongo 'users' collection stored in app.config."""
    return current_app.config["USERS_COLL"]

def _jwt_for(username: str) -> str:
    token = jwt.encode(
        {
            "username": username,
            "exp": datetime.datetime.now(datetime.timezone.utc)
                   + datetime.timedelta(days=30)
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256"
    )
    # PyJWT ≤ 2 can return bytes; normalise to str
    return token if isinstance(token, str) else token.decode("utf-8")

# ─────────────────────────── Routes ──────────────────────────────── #

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username, password = data.get("username"), data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    if _users().find_one({"username": username}):
        return jsonify({"message": "User already exist"}), 400

    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    _users().insert_one(
        {
            "username": username,
            "password": hashed_pw,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
    )
    return jsonify({"message": "User registered successfully",
                    "token": _jwt_for(username)}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username, password = data.get("username"), data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    user = _users().find_one({"username": username})
    if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
        return jsonify({"message": "Invalid username or password"}), 401

    return jsonify({"token": _jwt_for(username)}), 200
