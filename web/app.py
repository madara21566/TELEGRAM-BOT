import os, time, hmac, hashlib, io, zipfile
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from werkzeug.utils import secure_filename
from utils.stats import get_dashboard_data

app = Flask(__name__)
app.secret_key = os.getenv("FILEMANAGER_SECRET","madara_secret_key_786")

def fm_token(uid, proj, ts=None):
    secret = (os.getenv("FILEMANAGER_SECRET") or "madara_secret_key_786").encode()
    ts = ts or str(int(time.time())//3600); msg = f"{uid}:{proj}:{ts}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

def verify(uid, proj, token): return token == fm_token(uid, proj)

@app.route("/")
def home(): return "<h2>MADARA Running</h2>"

@app.route("/admin/dashboard")
def admin_dashboard():
    key = request.args.get("key")
    owner = os.getenv("OWNER_ID")
    if str(key) != str(owner): return "Unauthorized", 403
    data = get_dashboard_data()
    from flask import render_template
    return render_template("admin_dashboard.html", data=data)

@app.route("/admin/dashboard/json")
def admin_dashboard_json():
    key = request.args.get("key")
    owner = os.getenv("OWNER_ID")
    if str(key) != str(owner): return "Unauthorized", 403
    return jsonify(get_dashboard_data())
