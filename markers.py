# markers.py  —  blueprint REST per i Photo-Marker
import datetime as dt
import jwt
from bson import ObjectId
from functools import wraps
from flask import Blueprint, request, jsonify, current_app

markers_bp = Blueprint("markers", __name__)

# ───────────────────── Decoratore JWT ──────────────────────
def jwt_required(fn):
    """Verifica il token Bearer e inserisce request.username"""
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
                algorithms=["HS256"]
            )
            request.username = payload["sub"]            # <─ correzione: usa 'sub'
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Invalid token"}), 401
        return fn(*args, **kwargs)
    return wrapper


def _markers():
    """Riferimento rapido alla collection MongoDB"""
    return current_app.config["MARKERS_COLL"]

# ───────────────────── End-point CRUD ──────────────────────

@markers_bp.get("/")
@jwt_required
def list_markers():
    """
    GET /markers?updatedSince=<epoch-ms>
    Ritorna tutti i marker dell’utente; se updatedSince è presente,
    restituisce solo quelli modificati dal timestamp dato.
    """
    q = {"username": request.username, "deleted": False}

    since = request.args.get("updatedSince")
    if since is not None:
        try:
            millis = int(since)
            q["updated_at"] = {
                "$gte": dt.datetime.fromtimestamp(millis / 1000, dt.timezone.utc)
            }
        except ValueError:
            return jsonify({"message": "updatedSince must be epoch-millis"}), 400

    docs = _markers().find(q).sort("updated_at", 1)
    out = [{**doc, "_id": str(doc["_id"])} for doc in docs]
    return jsonify({"markers": out}), 200


@markers_bp.post("/")
@jwt_required
def create_marker():
    """
    POST /markers
    Richiede almeno lat, lng, title.
    Se il client manda 'id' viene usato come _id; altrimenti lo genera Mongo.
    """
    data = request.get_json(silent=True) or {}
    for f in ("lat", "lng", "title", "angle"):
        if f not in data:
            return jsonify({"message": f"{f} is required"}), 400

    # ── validazione numerica lat / lng ──
    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
        angle = float(data["angle"])
    except (ValueError, TypeError):
        return jsonify({"message": "lat/lng/angle must be numbers"}), 400

    now = dt.datetime.now(dt.timezone.utc)
    marker = {
        "_id": ObjectId(data.get("id")) if data.get("id") else ObjectId(),
        "username": request.username,
        "lat": lat,
        "lng": lng,
        "angle": angle,
        "title": data["title"],
        "genre": data.get("genre"),
        "settings": data.get("settings"),   # shutter, f-stop, iso…
        "tags": data.get("tags", []),
        "notes": data.get("notes"),
        "photoUrl": data.get("photoUrl"),
        "created_at": now,
        "updated_at": now,
        "deleted": False
    }

    _markers().insert_one(marker)
    marker["_id"] = str(marker["_id"])
    return jsonify({"marker": marker}), 201


@markers_bp.put("/<marker_id>")
@jwt_required
def update_marker(marker_id):
    """Aggiorna un marker; fallisce se non esiste o è già deleted=True."""
    data = request.get_json(silent=True) or {}
    now = dt.datetime.now(dt.timezone.utc)

    res = _markers().update_one(
        {"_id": ObjectId(marker_id), "username": request.username, "deleted": False},
        {"$set": {**data, "updated_at": now}}
    )
    if res.matched_count == 0:
        return jsonify({"message": "marker not found"}), 404
    return jsonify({"message": "updated"}), 200


@markers_bp.delete("/<marker_id>")
@jwt_required
def delete_marker(marker_id):
    """
    Soft-delete: marca deleted=True invece di rimuovere il documento.
    Così l’app offline può sincronizzare correttamente la cancellazione.
    """
    now = dt.datetime.now(dt.timezone.utc)
    res = _markers().update_one(
        {"_id": ObjectId(marker_id), "username": request.username, "deleted": False},
        {"$set": {"deleted": True, "updated_at": now}}
    )
    if res.matched_count == 0:
        return jsonify({"message": "marker not found"}), 404
    return jsonify({"message": "deleted"}), 200
