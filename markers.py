import datetime as dt
from functools import wraps

import jwt
import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request
from pymongo import ASCENDING, ReturnDocument

markers_bp = Blueprint("markers", __name__)

# ───────────────────────────────────────────────────────────
# Helpers Mongo / GridFS
# ───────────────────────────────────────────────────────────

def _markers():
    return current_app.config["MARKERS_COLL"]


def _fs():
    """Handle GridFS (collezione photos_fs)."""
    return gridfs.GridFS(current_app.config["DB"], collection="photos_fs")


def _parse_oid(value: str | None):
    """Converte una stringa in ObjectId; restituisce None se non valida."""
    try:
        return ObjectId(value) if value else None
    except (InvalidId, TypeError):
        return None


# ───────────────────────────────────────────────────────────
# TTL index (soft-delete)
# ───────────────────────────────────────────────────────────

def ensure_ttl_index():
    _markers().create_index(
        [("deleted_at", ASCENDING)],
        name="deleted_ttl_1days",
        expireAfterSeconds=60 * 60 * 24,
        partialFilterExpression={"deleted": True},
    )


# ───────────────────────────────────────────────────────────
# JWT decorator (ri-usato anche da photos.py)
# ───────────────────────────────────────────────────────────

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


# ───────────────────────────────────────────────────────────
# Utils mapping
# ───────────────────────────────────────────────────────────

def _millis(value):
    return int(value.timestamp() * 1000) if isinstance(value, dt.datetime) else 0


def _to_client(doc: dict) -> dict:
    """Trasforma documento Mongo → payload per l’app mobile."""
    return {
        "_id": str(doc["_id"]),
        "username": doc["username"],
        "lat": doc["lat"],
        "lng": doc["lng"],
        "title": doc["title"],
        "genre": doc.get("genre"),
        "shutterSpeed": doc.get("shutterSpeed"),
        "aperture": doc.get("aperture"),
        "iso": doc.get("iso"),
        "focalLength": doc.get("focalLength"),
        "tag": doc.get("tag"),
        "notes": doc.get("notes"),
        "photoIds": [str(pid) for pid in doc.get("photoIds", [])],
        # ▸ angle può essere None se mai impostato: uso or 0.0 per fallback sicuro
        "angle": float(doc.get("angle") or 0.0),
        "createdAt": _millis(doc.get("created_at")),
        "updatedAt": _millis(doc.get("updated_at")),
        "deleted": doc.get("deleted", False),
    }


# ───────────────────────────────────────────────────────────
# Routes
# ───────────────────────────────────────────────────────────


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

    # ▸ optional custom id dal client
    custom_id = _parse_oid(data.get("id"))
    if data.get("id") and custom_id is None:
        return jsonify({"message": "invalid id"}), 400

    now = dt.datetime.now(dt.timezone.utc)
    marker = {
        "_id": custom_id or ObjectId(),
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
        "photoIds": [],
        "angle": float(data.get("angle") or 0.0),
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
    data.pop("_id", None)  # evita l'errore 66

    oid = _parse_oid(marker_id)
    if oid is None:
        return jsonify({"message": "invalid id"}), 400

    if "angle" in data:
        try:
            data["angle"] = float(data["angle"] or 0.0)
        except (ValueError, TypeError):
            return jsonify({"message": "angle must be a number"}), 400

    now = dt.datetime.now(dt.timezone.utc)
    data["updated_at"] = now

    res = _markers().find_one_and_update(
        {"_id": oid, "username": request.username},
        {"$set": data},
        return_document=ReturnDocument.AFTER,
    )
    if not res:
        return jsonify({"message": "marker not found"}), 404
    return jsonify({"marker": _to_client(res)}), 200


@markers_bp.delete("/<marker_id>", strict_slashes=False)
@jwt_required
def delete_marker(marker_id):
    oid = _parse_oid(marker_id)
    if oid is None:
        return jsonify({"message": "invalid id"}), 400

    now = dt.datetime.now(dt.timezone.utc)
    res = _markers().find_one_and_update(
        {"_id": oid, "username": request.username},
        {"$set": {"deleted": True, "deleted_at": now, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if not res:
        return jsonify({"message": "marker not found"}), 404

    # ── elimina in cascata le immagini collegate (se presenti) ──
    if res.get("photoIds"):
        fs = _fs()
        for pid in res["photoIds"]:
            try:
                fs.delete(pid)
            except gridfs.NoFile:
                pass

    return jsonify({"marker": _to_client(res)}), 200
