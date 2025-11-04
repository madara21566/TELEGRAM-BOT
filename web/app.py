import os
import json
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "madara_secret_key_786"

# -----------------------------
# HOME PAGE (Fix 404 → “Bot Running ✅”)
# -----------------------------
@app.route('/')
def home():
    return "<h2 style='font-family:sans-serif;'>🤖 MADARA HOSTING BOT is Running ✅</h2><p>Server is alive and ready.</p>"

# -----------------------------
# FILE MANAGER UI
# -----------------------------
@app.route('/fm')
def file_manager():
    uid = request.args.get('uid')
    proj = request.args.get('proj')
    token = request.args.get('token')
    base_path = f"data/users/{uid}/{proj}"

    if not os.path.exists(base_path):
        return f"<h3>❌ Project not found for user {uid}.</h3>"

    files = []
    for root, dirs, filenames in os.walk(base_path):
        for fname in filenames:
            rel_path = os.path.relpath(os.path.join(root, fname), base_path)
            files.append(rel_path)

    return render_template("fm_index.html", files=files, uid=uid, proj=proj)

# -----------------------------
# FILE UPLOAD HANDLER
# -----------------------------
@app.route('/fm/upload', methods=['POST'])
def upload_file():
    uid = request.form.get('uid')
    proj = request.form.get('proj')
    base_path = f"data/users/{uid}/{proj}"
    os.makedirs(base_path, exist_ok=True)

    file = request.files['file']
    filename = secure_filename(file.filename)
    save_path = os.path.join(base_path, filename)
    file.save(save_path)
    return redirect(url_for('file_manager', uid=uid, proj=proj))

# -----------------------------
# FILE DOWNLOAD (for user)
# -----------------------------
@app.route('/fm/download')
def download_file():
    uid = request.args.get('uid')
    proj = request.args.get('proj')
    filename = request.args.get('filename')

    file_path = f"data/users/{uid}/{proj}/{filename}"
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "❌ File not found."

# -----------------------------
# FILE DELETE HANDLER
# -----------------------------
@app.route('/fm/delete')
def delete_file():
    uid = request.args.get('uid')
    proj = request.args.get('proj')
    filename = request.args.get('filename')
    file_path = f"data/users/{uid}/{proj}/{filename}"
    if os.path.exists(file_path):
        os.remove(file_path)
        return redirect(url_for('file_manager', uid=uid, proj=proj))
    return "❌ File not found."

# -----------------------------
# FILE EDIT PAGE
# -----------------------------
@app.route('/fm/edit', methods=['GET', 'POST'])
def edit_file():
    uid = request.args.get('uid')
    proj = request.args.get('proj')
    filename = request.args.get('filename')
    file_path = f"data/users/{uid}/{proj}/{filename}"

    if request.method == 'POST':
        new_content = request.form['content']
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return redirect(url_for('file_manager', uid=uid, proj=proj))

    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return render_template("fm_edit.html", filename=filename, content=content, uid=uid, proj=proj)
    else:
        return "❌ File not found."

# -----------------------------
# LOGS DOWNLOAD (New Fix)
# -----------------------------
@app.route('/logs/<uid>/<proj>')
def get_logs(uid, proj):
    path = f"data/users/{uid}/{proj}/logs.txt"
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "❌ No logs yet."

# -----------------------------
# PROJECT SCRIPT DOWNLOAD (New Fix)
# -----------------------------
@app.route('/download/<uid>/<proj>')
def download_script(uid, proj):
    path = f"data/users/{uid}/{proj}/project.zip"
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "❌ No project archive found."

# -----------------------------
# BACKUP DOWNLOAD (for admin)
# -----------------------------
@app.route('/backup/<uid>/<proj>')
def download_backup(uid, proj):
    backup_path = f"data/backups/{uid}_{proj}.zip"
    if os.path.exists(backup_path):
        return send_file(backup_path, as_attachment=True)
    return "❌ Backup not found."

# -----------------------------
# JSON STATUS CHECK (optional API)
# -----------------------------
@app.route('/status')
def status():
    return jsonify({
        "status": "running",
        "message": "MADARA HOSTING BOT Flask Web Server is active ✅"
    })

# -----------------------------
# MAIN APP RUN (Render uses this)
# -----------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
