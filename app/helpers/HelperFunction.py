from flask import Flask, request, jsonify, session
import hashlib
import random
import string
def responseData(status, message, data, status_res):
     return jsonify({
          "status": status, 
          "message": message,
          "data": data
        }), status_res

def hashing(data):
    hash_object = hashlib.sha256(data.encode('utf-8'))  
    return hash_object.hexdigest()


def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def generate_random_filename(file_extension):
    random_number = random.randint(100000000000000, 999999999999999)  # 15-digit random number
    return f"{random_number}{file_extension}"


def generate_random_string(length):
    characters = string.ascii_letters + string.digits  # Letters (upper & lower) + digits
    return ''.join(random.choice(characters) for _ in range(length))


