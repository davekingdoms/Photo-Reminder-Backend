#app.py
from flask import Flask
from pymongo import MongoClient
from datetime import timezone


app = Flask(__name__)
app.config["SECRET_KEY"] = "d6yw372%ylWK$u"          # use an env-var in prod

client = MongoClient("mongodb://localhost:27017",
    tz_aware=True,              
    tzinfo=timezone.utc)
db = client["photo_reminder"]

app.config["USERS_COLL"] = db["users"]
app.config["MARKERS_COLL"] = db["markers"]
app.config["DB"] = db

from auth import auth_bp, limiter         
from markers import markers_bp, ensure_ttl_index   
from photos import photos_bp

app.register_blueprint(auth_bp)  
app.register_blueprint(markers_bp, url_prefix="/markers")
app.register_blueprint(photos_bp) 

with app.app_context():
    ensure_ttl_index()

limiter.init_app(app)
  
@app.route("/")
def home():
    return "Server Flask attivo!"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)