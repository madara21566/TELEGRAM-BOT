import os
from flask import Flask, render_template, request, jsonify
from utils.stats import get_dashboard_data

app = Flask(__name__)
app.secret_key = os.getenv('FILEMANAGER_SECRET', 'madara_secret_key_786')

@app.route('/')
def home():
    return '<h2>MADARA Hosting Bot is running.</h2>'

@app.route('/admin/dashboard')
def admin_dashboard():
    key = request.args.get('key')
    owner = os.getenv('OWNER_ID')
    if str(key) != str(owner):
        return 'Unauthorized', 403
    data = get_dashboard_data()
    return render_template('admin_dashboard.html', data=data)

@app.route('/admin/dashboard/json')
def admin_dashboard_json():
    key = request.args.get('key')
    owner = os.getenv('OWNER_ID')
    if str(key) != str(owner):
        return 'Unauthorized', 403
    return jsonify(get_dashboard_data())
