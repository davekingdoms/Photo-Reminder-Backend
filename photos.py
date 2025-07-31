# photos.py

import datetime as dt
import io

import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, request, send_file, jsonify

from markers import jwt_required 

photos_bp = Blueprint("photos", __name__, url_prefix="")


def _fs():
   
    db = current_app.config["DB"]
 
    return gridfs.GridFS(db, collection="photos_fs")

@photos_bp.post("/markers/<marker_id>/photos")
@jwt_required
def upload_photos(marker_id):
   

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

    res = coll.update_one(
        {"_id": oid, "username": request.username},
        {
            "$addToSet": {"photoIds": {"$each": [pid for pid, _ in pairs]}},
            "$set": {"updated_at": dt.datetime.now(dt.timezone.utc)},
        },
    )
    if res.matched_count == 0:          
        for pid, _ in pairs:
            try:
                fs.delete(pid)
            except gridfs.NoFile:
                pass
        return jsonify({"message": "marker update failed"}), 409

    return jsonify({
        "photos": [
            {"filename": fname, "_id": str(pid)}
            for pid, fname in pairs
        ]
    }), 201



@photos_bp.get("/photos/<photo_id>")
@jwt_required
def get_photo(photo_id):
    fs = _fs()

    try:
        oid = ObjectId(photo_id)
    except (InvalidId, TypeError):
        return jsonify({"message": "invalid id"}), 400

    try:
        grid_file = fs.get(oid)
    except gridfs.NoFile:
        return jsonify({"message": "photo not found"}), 404

    meta = grid_file.metadata or {}
    if meta.get("username") != request.username:
        return jsonify({"message": "forbidden"}), 403

    return send_file(
        io.BytesIO(grid_file.read()),
        mimetype=grid_file.content_type or "application/octet-stream",
        download_name=grid_file.filename or f"{photo_id}.jpg",
    )
