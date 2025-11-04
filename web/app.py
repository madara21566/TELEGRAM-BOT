from flask import Flask, render_template, request, send_file, abort, redirect, url_for
import secrets, time, json, os, shutil
from pathlib import Path

app = Flask(__name__, template_folder="templates", static_folder="static")
TOKENS_FILE = Path("data/fm_tokens.json")

def load_tokens():
    if TOKENS_FILE.exists():
        try:
            return json.loads(TOKENS_FILE.read_text(encoding='utf-8'))
        except:
            return {}
    return {}

def save_tokens(t):
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(t), encoding='utf-8')

def create_fm_token(uid, proj, lifetime_seconds=3600):
    tokens = load_tokens()
    token = secrets.token_urlsafe(16)
    tokens[token] = {"uid": int(uid), "proj": proj, "expiry": int(time.time()) + lifetime_seconds}
    save_tokens(tokens)
    return token

def validate_fm_token(token, uid, proj):
    tokens = load_tokens()
    info = tokens.get(token)
    if not info: return False
    if info["uid"] != int(uid) or info["proj"] != proj: return False
    if int(time.time()) > info["expiry"]:
        tokens.pop(token, None); save_tokens(tokens); return False
    return True

@app.route('/fm')
def fm_index():
    uid = request.args.get('uid'); proj = request.args.get('proj'); token = request.args.get('token')
    if not (uid and proj and token): return "Invalid request", 400
    if not validate_fm_token(token, int(uid), proj): return "Invalid or expired token", 403
    base = Path(f"data/users/{uid}/{proj}")
    if not base.exists(): return "Project not found", 404
    files = sorted([p.name for p in base.iterdir() if p.is_file()])
    return render_template("fm_index.html", files=files, uid=uid, proj=proj, token=token, base_url=request.url_root.rstrip('/'))

@app.route('/fm/download')
def fm_download():
    uid = request.args.get('uid'); proj = request.args.get('proj'); file = request.args.get('file'); token = request.args.get('token')
    if not validate_fm_token(token, int(uid), proj): abort(403)
    p = Path(f"data/users/{uid}/{proj}/{file}")
    if not p.exists(): abort(404)
    return send_file(str(p), as_attachment=True, download_name=p.name)

@app.route('/fm/upload', methods=['POST'])
def fm_upload():
    uid = request.form.get('uid'); proj = request.form.get('proj'); token = request.form.get('token')
    if not validate_fm_token(token, int(uid), proj): abort(403)
    f = request.files.get('file')
    if not f: return "No file", 400
    base = Path(f"data/users/{uid}/{proj}"); base.mkdir(parents=True, exist_ok=True)
    dest = base / f.filename
    f.save(str(dest))
    if dest.suffix.lower() == '.zip':
        try:
            import zipfile
            with zipfile.ZipFile(str(dest),'r') as z: z.extractall(path=str(base))
            dest.unlink()
        except Exception:
            pass
    return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")

@app.route('/fm/edit')
def fm_edit():
    uid = request.args.get('uid'); proj = request.args.get('proj'); file = request.args.get('file'); token = request.args.get('token')
    if not validate_fm_token(token, int(uid), proj): abort(403)
    p = Path(f"data/users/{uid}/{proj}/{file}")
    if not p.exists(): abort(404)
    content = p.read_text(errors='ignore')
    return render_template("fm_edit.html", uid=uid, proj=proj, file=file, token=token, content=content)

@app.route('/fm/save', methods=['POST'])
def fm_save():
    uid = request.form.get('uid'); proj = request.form.get('proj'); file = request.form.get('file'); token = request.form.get('token'); content = request.form.get('content')
    if not validate_fm_token(token, int(uid), proj): abort(403)
    p = Path(f"data/users/{uid}/{proj}/{file}")
    p.write_text(content, encoding='utf-8')
    return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")

@app.route('/fm/delete')
def fm_delete():
    uid = request.args.get('uid'); proj = request.args.get('proj'); file = request.args.get('file'); token = request.args.get('token')
    if not validate_fm_token(token, int(uid), proj): abort(403)
    p = Path(f"data/users/{uid}/{proj}/{file}")
    if p.exists(): p.unlink()
    return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")

@app.route('/fm/delete_project')
def fm_delete_project():
    uid = request.args.get('uid'); proj = request.args.get('proj'); token = request.args.get('token')
    if not validate_fm_token(token, int(uid), proj): abort(403)
    base = Path(f"data/users/{uid}/{proj}")
    if base.exists(): shutil.rmtree(str(base))
    return f"Deleted {proj}"

def run_flask(port=10000):
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', port)), debug=False, use_reloader=False)
