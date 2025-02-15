from flask import Flask, request, jsonify
from pymongo import MongoClient
import bcrypt
import jwt
import datetime
import string
from functools import wraps

app = Flask(__name__)

app.config['SECRET_KEY'] = 'd6yw372%ylWK$u'
client = MongoClient("mongodb://localhost:27017")
db = client["photo_reminder"]
users_collection = db["users"]

@app.route('/register', methods = ['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON received"}), 400

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400
    
    existing_user = users_collection.find_one({"email": email})
    if existing_user:
        return jsonify({"message": "User already exist"}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    user_doc = {
        "email": email,
        "password": hashed_password,
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }

    users_collection.insert_one(user_doc)

    return jsonify({"message": "User registered successfully"}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON received"}), 400

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400
    
    user = users_collection.find_one({"email": email})
    if not user:
        return jsonify({"message": "Invalid email or password"}), 401
    
    if bcrypt.checkpw(password.encode('utf-8'), user['password']):
        token = jwt.encode(
            {
                "email": email,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
            },
            app.config['SECRET_KEY'],
            algorithm = "HS256"
        )

        token_str = token if isinstance(token, str) else token.decode('utf-8')
        return jsonify({"token": token_str}), 200
    
    else:
        return jsonify({"message": "Invalid email or password"}), 401

   
@app.route("/")
def home():
    return "Server Flask attivo!"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)