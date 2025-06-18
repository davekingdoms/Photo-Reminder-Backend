#auth.py
import datetime, bcrypt, jwt
from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

auth_bp = Blueprint("auth", __name__)
limiter = Limiter(key_func=get_remote_address)


# ───────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────

def _users():
    """Restituisce la collection MongoDB degli utenti"""
    return current_app.config["USERS_COLL"]


def _jwt_for(username: str) -> str:
    """Genera e restituisce un JWT HS256 valido 30 giorni."""
    token = jwt.encode(
        {
            "sub": username,
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=30),
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    # jwt.encode in PyJWT >= 2.x restituisce str, in 1.x bytes → normalizzo
    return token if isinstance(token, str) else token.decode("utf-8")


# ───────────────────────────────────────────────────────────
# Routes
# ───────────────────────────────────────────────────────────


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
            "username": username,
            "password": hashed_pw,  # salvato come BSON Binary
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "failed_attempts": 0,
            "lockout_until": None,
        }
    )

    return (
        jsonify({"message": "User registered successfully", "token": _jwt_for(username)}),
        201,
    )


@auth_bp.post("/login")
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    now = datetime.datetime.now(datetime.timezone.utc)
    user = _users().find_one({"username": username})
    if not user:
        return jsonify({"message": "Invalid username or password"}), 401

    lockout_until = user.get("lockout_until")
    if lockout_until and lockout_until > now:
        remaining = int((lockout_until - now).total_seconds() / 60)
        return (
            jsonify({"message": f"Account temporarily locked. Try again in {remaining} minutes."}),
            429,
        )

    # -----------------------------------------------------------
    # SAFE PASSWORD CHECK (fix 1.5): cast BSON Binary → bytes
    # -----------------------------------------------------------
    stored_pw = bytes(user["password"])  # rimuove il wrapper Binary
    if not bcrypt.checkpw(password.encode(), stored_pw):
        # incrementa i tentativi falliti
        attempts = user.get("failed_attempts", 0) + 1
        update = {"failed_attempts": attempts}

        # dopo 5 tentativi, blocca per 15 minuti
        if attempts >= 5:
            update["lockout_until"] = now + datetime.timedelta(minutes=15)
            update["failed_attempts"] = 0

        _users().update_one({"_id": user["_id"]}, {"$set": update})
        return jsonify({"message": "Invalid username or password"}), 401

    # Login riuscito: resetta contatori e genera token
    _users().update_one(
        {"_id": user["_id"]}, {"$set": {"failed_attempts": 0, "lockout_until": None}}
    )

    return jsonify({"token": _jwt_for(username), "username": username}), 200
