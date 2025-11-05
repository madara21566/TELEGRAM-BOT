import os, time, hmac, hashlib, io, zipfile
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from werkzeug.utils import secure_filename
app = Flask(__name__); app.secret_key = os.getenv("FILEMANAGER_SECRET","madara_secret_key_786")
def fm_token(uid, proj, ts=None):
    secret = (os.getenv("FILEMANAGER_SECRET") or "madara_secret_key_786").encode()
    ts = ts or str(int(time.time())//3600); msg = f"{uid}:{proj}:{ts}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()
def verify(uid, proj, token): return token == fm_token(uid, proj)
@app.route("/") 
def home(): return "<h2>🤖 MADARA HOSTING BOT is Running ✅</h2>"
@app.route("/status")
def status(): return jsonify({"status":"ok","message":"running"})
@app.route("/fm")
def fm_index():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token")
    if not verify(uid, proj, token): return "Unauthorized", 401
    base = f"data/users/{uid}/{proj}"
    if not os.path.exists(base): return "Project not found", 404
    files=[]; 
    for r,d,fs in os.walk(base):
        for f in fs: files.append(os.path.relpath(os.path.join(r,f), base))
    files.sort()
    return render_template("fm_index.html", uid=uid, proj=proj, files=files, token=token)
@app.route("/fm/upload", methods=["POST"])
def fm_upload():
    uid = request.form.get("uid"); proj = request.form.get("proj"); token = request.form.get("token")
    if not verify(uid, proj, token): return "Unauthorized", 401
    base = f"data/users/{uid}/{proj}"; os.makedirs(base, exist_ok=True)
    f = request.files.get("file")
    if f:
        name = secure_filename(f.filename); f.save(os.path.join(base,name))
    return redirect(url_for("fm_index", uid=uid, proj=proj, token=token))
@app.route("/fm/download")
def fm_download():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token"); path = request.args.get("path")
    if not verify(uid, proj, token): return "Unauthorized", 401
    base = f"data/users/{uid}/{proj}"; fp = os.path.join(base, path)
    if os.path.exists(fp): return send_file(fp, as_attachment=True)
    return "Not found", 404
@app.route("/fm/delete")
def fm_delete():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token"); path = request.args.get("path")
    if not verify(uid, proj, token): return "Unauthorized", 401
    base = f"data/users/{uid}/{proj}"; fp = os.path.join(base, path)
    if os.path.exists(fp): os.remove(fp)
    return redirect(url_for("fm_index", uid=uid, proj=proj, token=token))
@app.route("/fm/edit", methods=["GET","POST"])
def fm_edit():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token"); path = request.args.get("path")
    if not verify(uid, proj, token): return "Unauthorized", 401
    base = f"data/users/{uid}/{proj}"; fp = os.path.join(base, path)
    if request.method == "POST":
        text = request.form.get("content",""); os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp,"w",encoding="utf-8") as f: f.write(text)
        return redirect(url_for("fm_index", uid=uid, proj=proj, token=token))
    content = open(fp,"r",encoding="utf-8",errors="ignore").read() if os.path.exists(fp) else ""
    return render_template("fm_edit.html", uid=uid, proj=proj, path=path, token=token, content=content)
@app.route("/logs/<uid>/<proj>")
def logs(uid, proj):
    path = f"data/users/{uid}/{proj}/logs.txt"
    if os.path.exists(path): return send_file(path, as_attachment=True)
    return "No logs yet.", 404
@app.route("/download/<uid>/<proj>")
def download_project(uid, proj):
    base = f"data/users/{uid}/{proj}"
    if not os.path.exists(base): return "Not found", 404
    mem = io.BytesIO()
    with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as z:
        for r, d, fs in os.walk(base):
            for f in fs:
                p = os.path.join(r,f); z.write(p, os.path.relpath(p, base))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=f"{proj}.zip")
