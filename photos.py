# photos.py
"""
Gestione upload / download immagini con GridFS.

POST  /markers/<marker_id>/photos       (multipart)  →  { "photoIds": [...] }
GET   /photos/<photo_id>                              →  stream immagine
"""
import datetime as dt
import io
from bson import ObjectId
import gridfs
from flask import Blueprint, current_app, request, send_file, jsonify

from markers import jwt_required     # ri-usa il decorator già definito

photos_bp = Blueprint("photos", __name__, url_prefix="")

def _fs():
    """Restituisce un handle GridFS (collezione 'photos_fs')."""
    db = current_app.config["DB"]
    # un solo oggetto; gridfs.GridFS è leggero, possiamo ricrearlo a richiesta
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
    • fa push degli _id nel campo photoIds del marker
    """
    files = request.files.getlist("files")
    if not files:
        return jsonify({"message": "no files provided"}), 400

    fs  = _fs()
    ids = []

    for f in files:
        # extra check: max 25 MB per file
        f.seek(0, io.SEEK_END)
        if f.tell() > 25 * 1024 * 1024:
            return jsonify({"message": f"{f.filename} too large"}), 400
        f.seek(0)

        _id = fs.put(
            f,                              # file-like object
            filename=f.filename,
            content_type=f.mimetype,
            metadata={
                "username":  request.username,
                "marker_id": marker_id,
                "created_at": dt.datetime.utcnow(),
            },
        )
        ids.append(_id)

    # aggiunge gli id al marker (array unico, evita duplicati)
    coll = current_app.config["MARKERS_COLL"]
    coll.update_one(
        {"_id": ObjectId(marker_id), "username": request.username},
        {
            "$addToSet": {"photoIds": {"$each": ids}},
            "$set":      {"updated_at": dt.datetime.utcnow()},
        },
    )

    return jsonify({"photoIds": [str(x) for x in ids]}), 201


# ────────────────────────────────────────────────────────────────
# DOWNLOAD (stream) di una immagine
# ────────────────────────────────────────────────────────────────
@photos_bp.get("/photos/<photo_id>")
@jwt_required      
def get_photo(photo_id):
    fs = _fs()
    try:
        grid_file = fs.get(ObjectId(photo_id))
    except gridfs.NoFile:
        return jsonify({"message": "photo not found"}), 404

    return send_file(
        io.BytesIO(grid_file.read()),
        mimetype=grid_file.content_type or "application/octet-stream",
        download_name=grid_file.filename or f"{photo_id}.jpg",
    )
