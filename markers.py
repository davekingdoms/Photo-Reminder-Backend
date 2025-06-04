import datetime as dt
from functools import wraps

import jwt
from bson import ObjectId
from flask import Blueprint, current_app, jsonify, request
from pymongo import ASCENDING

markers_bp = Blueprint("markers", __name__)

# ────────────────────────────────────────────────────────────
# Init: crea (una volta) l’indice TTL per i soft-delete
# ────────────────────────────────────────────────────────────
def _markers():
    return current_app.config["MARKERS_COLL"]

def ensure_ttl_index():

    _markers().create_index(
        [("deleted_at", ASCENDING)],         
        name="deleted_ttl_1day",
        expireAfterSeconds=60 * 60 * 24 * 15,    
        partialFilterExpression={"deleted": True},
    )

# ────────────────────────────────────────────────────────────
# JWT decorator
# ────────────────────────────────────────────────────────────
def jwt_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"message": "Token missing"}), 401

        token = auth.split(maxsplit=1)[1]
        try:
            payload = jwt.decode(
                token,
                current_app.config["SECRET_KEY"],
                algorithms=["HS256"],
            )
            request.username = payload["sub"]
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Invalid token"}), 401

        return fn(*args, **kwargs)

    return wrapper


def _millis(value):
    """datetime → epoch-millis"""
    if isinstance(value, dt.datetime):
        return int(value.timestamp() * 1000)
    return value or 0


def _to_client(doc: dict) -> dict:
    """Mappa un documento MongoDB nel payload per l’app"""
    return {
        "_id": str(doc["_id"]),
        "username": doc["username"],
        "lat": doc["lat"],
        "lng": doc["lng"],
        "title": doc["title"],
        "genre": doc.get("genre"),
        "shutterSpeed": doc.get("shutterSpeed") or (doc.get("settings") or {}).get("shutterSpeed"),
        "aperture": doc.get("aperture") or (doc.get("settings") or {}).get("aperture"),
        "iso": doc.get("iso") or (doc.get("settings") or {}).get("iso"),
        "focalLength": doc.get("focalLength") or (doc.get("settings") or {}).get("focalLength"),
        "tag": doc.get("tag") or (doc.get("tags") or [None])[0],
        "notes": doc.get("notes"),
        "photoUrl": doc.get("photoUrl"),
        "angle": float(doc.get("angle", 0.0)),
        "createdAt": _millis(doc.get("created_at")),
        "updatedAt": _millis(doc.get("updated_at")),
        "deleted": doc.get("deleted", False),
    }

# ────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────
@markers_bp.get("/", strict_slashes=False)
@jwt_required
def list_markers():
    q = {"username": request.username}

    if (since := request.args.get("updatedSince")) is not None:
        try:
            millis = int(since)
            q["updated_at"] = {
                "$gte": dt.datetime.fromtimestamp(millis / 1000, dt.timezone.utc)
            }
        except ValueError:
            return jsonify({"message": "updatedSince must be epoch-millis"}), 400

    docs = _markers().find(q).sort("updated_at", 1)
    return jsonify({"markers": [_to_client(d) for d in docs]}), 200


@markers_bp.post("/", strict_slashes=False)
@jwt_required
def create_marker():
    data = request.get_json(silent=True) or {}
    for f in ("lat", "lng", "title"):
        if f not in data:
            return jsonify({"message": f"{f} is required"}), 400

    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (ValueError, TypeError):
        return jsonify({"message": "lat/lng must be numbers"}), 400

    now = dt.datetime.now(dt.timezone.utc)
    marker = {
        "_id": ObjectId(data.get("id")) if data.get("id") else ObjectId(),
        "username": request.username,
        "lat": lat,
        "lng": lng,
        "title": data["title"],
        "genre": data.get("genre"),
        "shutterSpeed": data.get("shutterSpeed"),
        "aperture": data.get("aperture"),
        "iso": data.get("iso"),
        "focalLength": data.get("focalLength"),
        "tag": data.get("tag"),
        "notes": data.get("notes"),
        "photoUrl": data.get("photoUrl"),
        "angle": float(data.get("angle", 0.0)),
        "created_at": now,
        "updated_at": now,
        "deleted": False,
    }
    _markers().insert_one(marker)
    return jsonify({"marker": _to_client(marker)}), 201


@markers_bp.put("/<marker_id>", strict_slashes=False)
@jwt_required
def update_marker(marker_id):
    data = request.get_json(silent=True) or {}
    now = dt.datetime.now(dt.timezone.utc)

    if "angle" in data:
        try:
            data["angle"] = float(data["angle"])
        except (ValueError, TypeError):
            return jsonify({"message": "angle must be a number"}), 400

    data["updated_at"] = now

    res = _markers().find_one_and_update(
        {"_id": ObjectId(marker_id), "username": request.username},
        {"$set": data},
        return_document=True,          # restituisce il doc aggiornato
    )
    if not res:
        return jsonify({"message": "marker not found"}), 404
    return jsonify({"marker": _to_client(res)}), 200   # wrapper coerente


@markers_bp.delete("/<marker_id>", strict_slashes=False)
@jwt_required
def delete_marker(marker_id):
    now = dt.datetime.now(dt.timezone.utc)
    res = _markers().find_one_and_update(
        {"_id": ObjectId(marker_id), "username": request.username},
        {"$set": {
            "deleted": True,
            "deleted_at": now,          # necessario per TTL
            "updated_at": now
        }},
        return_document=True,
    )
    if not res:
        return jsonify({"message": "marker not found"}), 404
    return jsonify({"marker": _to_client(res)}), 200
