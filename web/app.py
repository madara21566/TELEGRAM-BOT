import os, hmac, hashlib, time, io, zipfile
from flask import Flask, render_template, request, send_from_directory, jsonify, abort
from utils.stats import get_dashboard_data

app = Flask(__name__)
app.secret_key = os.getenv('FILEMANAGER_SECRET','madara_secret_key_786')

BASE_DIR = "data/users"

def valid_token(uid, proj, token):
    secret = (os.getenv("FILEMANAGER_SECRET") or "madara_secret_key_786").encode()
    ts = str(int(time.time())//3600)
    check = hmac.new(secret, f"{uid}:{proj}:{ts}".encode(), hashlib.sha256).hexdigest()
    return token == check

@app.route("/")
def home():
    return "<h3>MADARA Hosting Bot Running ✓</h3>"

@app.route("/admin/dashboard")
def admin_dashboard():
    key = request.args.get("key")
    if key != os.getenv("OWNER_ID"):
        return "Unauthorized", 403
    data = get_dashboard_data()
    return render_template("admin_dashboard.html", data=data)

# FILE MANAGER ✔️
@app.route("/fm")
def fm():
    uid = request.args.get("uid")
    proj = request.args.get("proj")
    token = request.args.get("token")

    if not valid_token(uid, proj, token):
        return "Invalid Access", 403

    proj_path = os.path.join(BASE_DIR, uid, proj)
    if not os.path.exists(proj_path):
        return "Project not found", 404

    files = []
    for f in os.listdir(proj_path):
        files.append(f"<li><a href='/fm/download?uid={uid}&proj={proj}&file={f}'>{f}</a></li>")

    return f"""
    <h3>📂 File Manager - {proj}</h3>
    <ul>{''.join(files)}</ul>
    <hr>
    <form action="/fm/upload" method="post" enctype="multipart/form-data">
        <input type="hidden" name="uid" value="{uid}">
        <input type="hidden" name="proj" value="{proj}">
        <input type="hidden" name="token" value="{token}">
        <input type="file" name="file">
        <button type="submit">Upload</button>
    </form>
    """

@app.route("/fm/upload", methods=["POST"])
def upload_file():
    uid = request.form.get("uid")
    proj = request.form.get("proj")
    token = request.form.get("token")

    if not valid_token(uid, proj, token):
        return "Invalid Access", 403

    f = request.files["file"]
    proj_path = os.path.join(BASE_DIR, uid, proj)
    f.save(os.path.join(proj_path, f.filename))
    return "<script>alert('Uploaded Successfully!'); history.back();</script>"

@app.route("/fm/download")
def download():
    uid = request.args.get("uid")
    proj = request.args.get("proj")
    token = request.args.get("token")
    filename = request.args.get("file")

    if not valid_token(uid, proj, token):
        return "Invalid Access", 403

    return send_from_directory(os.path.join(BASE_DIR, uid, proj), filename, as_attachment=True)
