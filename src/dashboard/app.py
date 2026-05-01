from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import json, os

app = Flask(__name__, static_folder='static')
CORS(app)

@app.route('/api/leads')
def get_leads():
    path = os.path.join(os.path.dirname(__file__), '../../leads_final.json')
    with open(path, encoding='utf-8') as f:
        return jsonify(json.load(f))

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    app.run(port=5050, debug=True)
