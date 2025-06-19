# photos.py
"""
Gestione upload / download immagini con GridFS.

POST  /markers/<marker_id>/photos       (multipart)  →  { "photoIds": [...] }
GET   /photos/<photo_id>                              →  stream immagine
"""
import datetime as dt
import io

import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, request, send_file, jsonify

from markers import jwt_required  # ri-usa il decorator già definito

photos_bp = Blueprint("photos", __name__, url_prefix="")


def _fs():
    """Restituisce un handle GridFS (collezione 'photos_fs')."""
    db = current_app.config["DB"]
    # GridFS è leggero: possiamo creare un'istanza per request
    return gridfs.GridFS(db, collection="photos_fs")


# ────────────────────────────────────────────────────────────────
# UPLOAD di (una o più) immagini per un marker
# ────────────────────────────────────────────────────────────────
@photos_bp.post("/markers/<marker_id>/photos")
@jwt_required
def upload_photos(marker_id):
    """
    • accetta N file multipart con name="files"
    • salva ogni immagine in GridFS
    • aggiorna photoIds nel marker
    • restituisce lista {filename,_id}
    """
    # ---------- 1. validazione id & ownership ----------
    try:
        oid = ObjectId(marker_id)
    except (InvalidId, TypeError):
        return jsonify({"message": "invalid id"}), 400

    coll = current_app.config["MARKERS_COLL"]
    marker = coll.find_one(
        {"_id": oid, "username": request.username, "deleted": {"$ne": True}}
    )
    if not marker:
        return jsonify({"message": "marker not found"}), 404

    # ---------- 2. payload ----------
    files = request.files.getlist("files")
    if not files:
        return jsonify({"message": "no files provided"}), 400

    fs, pairs = _fs(), []          # [(ObjectId, filename)]
    for f in files:
        f.seek(0, io.SEEK_END)
        if f.tell() > 25 * 1024 * 1024:
            return jsonify({"message": f"{f.filename} too large"}), 400
        f.seek(0)

        _id = fs.put(
            f,
            filename=f.filename,
            content_type=f.mimetype,
            metadata={
                "username": request.username,
                "marker_id": str(oid),
                "created_at": dt.datetime.now(dt.timezone.utc),
            },
        )
        pairs.append((_id, f.filename))

    # ---------- 3. update marker ----------
    res = coll.update_one(
        {"_id": oid, "username": request.username},
        {
            "$addToSet": {"photoIds": {"$each": [pid for pid, _ in pairs]}},
            "$set": {"updated_at": dt.datetime.now(dt.timezone.utc)},
        },
    )
    if res.matched_count == 0:             # race-condition: rollback
        for pid, _ in pairs:
            try:
                fs.delete(pid)
            except gridfs.NoFile:
                pass
        return jsonify({"message": "marker update failed"}), 409

    # ---------- 4. risposta stabile ----------
    return jsonify({
        "photos": [
            {"filename": fname, "_id": str(pid)}
            for pid, fname in pairs
        ]
    }), 201


# ────────────────────────────────────────────────────────────────
# DOWNLOAD (stream) di una immagine
# ────────────────────────────────────────────────────────────────
@photos_bp.get("/photos/<photo_id>")
@jwt_required
def get_photo(photo_id):
    fs = _fs()

    # ▶︎ 1.3  — validazione ObjectId
    try:
        oid = ObjectId(photo_id)
    except (InvalidId, TypeError):
        return jsonify({"message": "invalid id"}), 400

    try:
        grid_file = fs.get(oid)
    except gridfs.NoFile:
        return jsonify({"message": "photo not found"}), 404

    # ▶︎ 1.4  — verifica ownership
    meta = grid_file.metadata or {}
    if meta.get("username") != request.username:
        return jsonify({"message": "forbidden"}), 403

    return send_file(
        io.BytesIO(grid_file.read()),
        mimetype=grid_file.content_type or "application/octet-stream",
        download_name=grid_file.filename or f"{photo_id}.jpg",
    )
