from flask import Flask
from pymongo import MongoClient

# ------------------------------------------------------------------ #
# App & DB initialisation
# ------------------------------------------------------------------ #
app = Flask(__name__)
app.config["SECRET_KEY"] = "d6yw372%ylWK$u"          # ⚠️ use an env-var in prod

client = MongoClient("mongodb://localhost:27017")
db = client["photo_reminder"]
# Store the collections inside app.config so blueprints can access them
app.config["USERS_COLL"] = db["users"]
app.config["MARKERS_COLL"] = db["markers"] # Nuova collezione per i marker

# ------------------------------------------------------------------ #
# Register blueprints
# ------------------------------------------------------------------ #
from auth import auth_bp          # importiamo auth.py
from markers import markers_bp    # importiamo il nuovo file markers.py

app.register_blueprint(auth_bp)   # Registriamo il blueprint auth
app.register_blueprint(markers_bp, url_prefix="/markers")

# ------------------------------------------------------------------ #
# Simple health check
# ------------------------------------------------------------------ #
@app.route("/")
def home():
    return "Server Flask attivo!"

# ------------------------------------------------------------------ #
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)