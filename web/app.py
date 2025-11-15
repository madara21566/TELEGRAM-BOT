import os
import time
import hmac
import hashlib
import io
import zipfile

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    redirect,
    url_for,
    abort,
)

from utils.stats import get_dashboard_data

app = Flask(__name__)
app.secret_key = os.getenv("FILEMANAGER_SECRET", "madara_secret_key_786")


# ---------- COMMON HELPERS ---------- #

def _project_base(uid, proj):
    return os.path.join("data", "users", str(uid), proj)


def _verify_token(uid, proj, token):
    """
    Same logic as _fm_link in project_handler.py
    Token = HMAC( secret, f"{uid}:{proj}:{ts}" ) with ts = current hour
    """
    secret = (os.getenv("FILEMANAGER_SECRET") or "madara_secret_key_786").encode()
    ts = str(int(time.time()) // 3600)
    expected = hmac.new(
        secret,
        f"{uid}:{proj}:{ts}".encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, token or "")


def _safe_join_project(uid, proj, relpath=""):
    base = os.path.realpath(_project_base(uid, proj))
    full = os.path.realpath(os.path.join(base, relpath or ""))
    if not full.startswith(base):
        abort(403)
    return base, full


# ---------- HOME + DASHBOARD ---------- #

@app.route("/")
def home():
    return "<h2>MADARA Hosting Bot is running.</h2>"


@app.route("/admin/dashboard")
def admin_dashboard():
    key = request.args.get("key")
    owner = os.getenv("OWNER_ID")
    if str(key) != str(owner):
        return "Unauthorized", 403
    data = get_dashboard_data()
    return render_template("admin_dashboard.html", data=data)


@app.route("/admin/dashboard/json")
def admin_dashboard_json():
    key = request.args.get("key")
    owner = os.getenv("OWNER_ID")
    if str(key) != str(owner):
        return "Unauthorized", 403
    return jsonify(get_dashboard_data())


# ---------- PROJECT ZIP DOWNLOAD (for Telegram button) ---------- #

@app.route("/download/<uid>/<proj>")
def download_project(uid, proj):
    base = _project_base(uid, proj)
    if not os.path.exists(base):
        abort(404)
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(base):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, base))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{proj}.zip",
    )


# ---------- FILE MANAGER MAIN PAGE ---------- #

@app.route("/fm", methods=["GET"])
def file_manager():
    uid = request.args.get("uid")
    proj = request.args.get("proj")
    token = request.args.get("token", "")
    relpath = request.args.get("path", "")

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    base, full = _safe_join_project(uid, proj, relpath)

    # if target is file -> redirect to editor
    if os.path.isfile(full):
        return redirect(url_for("fm_edit", uid=uid, proj=proj, token=token, path=relpath))

    # ensure directory exists
    if not os.path.exists(full):
        os.makedirs(full, exist_ok=True)

    entries = []
    for name in sorted(os.listdir(full)):
        p = os.path.join(full, name)
        rel = os.path.relpath(p, base)
        entries.append(
            {
                "name": name,
                "rel": rel,
                "is_dir": os.path.isdir(p),
                "size": os.path.getsize(p) if os.path.isfile(p) else None,
                "mtime": time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(os.path.getmtime(p)),
                ),
            }
        )

    # parent folder
    parent = None
    if os.path.realpath(full) != os.path.realpath(base):
        parent_rel = os.path.relpath(os.path.dirname(full), base)
        if parent_rel == ".":
            parent_rel = ""
        parent = parent_rel

    return render_template(
        "file_manager.html",
        uid=uid,
        proj=proj,
        token=token,
        path=relpath,
        entries=entries,
        parent=parent,
        edit_mode=False,
        file_content="",
        file_name="",
    )


# ---------- FILE EDITOR ---------- #

@app.route("/fm/edit", methods=["GET"])
def fm_edit():
    uid = request.args.get("uid")
    proj = request.args.get("proj")
    token = request.args.get("token", "")
    relpath = request.args.get("path", "")

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    base, full = _safe_join_project(uid, proj, relpath)
    if not os.path.isfile(full):
        abort(404)

    try:
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        content = f"ERROR READING FILE: {e}"

    dir_rel = os.path.dirname(relpath)

    return render_template(
        "file_manager.html",
        uid=uid,
        proj=proj,
        token=token,
        path=dir_rel,
        entries=[],
        parent=dir_rel,
        edit_mode=True,
        file_content=content,
        file_name=relpath,
    )


@app.route("/fm/save", methods=["POST"])
def fm_save():
    uid = request.form.get("uid")
    proj = request.form.get("proj")
    token = request.form.get("token", "")
    relpath = request.form.get("path", "")
    content = request.form.get("content", "")

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    base, full = _safe_join_project(uid, proj, relpath)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)

    folder_rel = os.path.dirname(relpath)
    return redirect(
        url_for("file_manager", uid=uid, proj=proj, token=token, path=folder_rel)
    )


# ---------- FILE OPERATIONS: UPLOAD / MKDIR / NEWFILE / DELETE / RENAME / DOWNLOAD ---------- #

@app.route("/fm/upload", methods=["POST"])
def fm_upload():
    uid = request.form.get("uid")
    proj = request.form.get("proj")
    token = request.form.get("token", "")
    relpath = request.form.get("path", "")

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    base, full = _safe_join_project(uid, proj, relpath)

    file = request.files.get("file")
    if file and file.filename:
        dst = os.path.join(full, file.filename)
        file.save(dst)

    return redirect(
        url_for("file_manager", uid=uid, proj=proj, token=token, path=relpath)
    )


@app.route("/fm/mkdir", methods=["POST"])
def fm_mkdir():
    uid = request.form.get("uid")
    proj = request.form.get("proj")
    token = request.form.get("token", "")
    relpath = request.form.get("path", "")
    name = request.form.get("name", "").strip()

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    if not name:
        return redirect(
            url_for("file_manager", uid=uid, proj=proj, token=token, path=relpath)
        )

    base, full = _safe_join_project(uid, proj, relpath)
    os.makedirs(os.path.join(full, name), exist_ok=True)

    return redirect(
        url_for("file_manager", uid=uid, proj=proj, token=token, path=relpath)
    )


@app.route("/fm/newfile", methods=["POST"])
def fm_newfile():
    uid = request.form.get("uid")
    proj = request.form.get("proj")
    token = request.form.get("token", "")
    relpath = request.form.get("path", "")
    name = request.form.get("name", "").strip()

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    if not name:
        return redirect(
            url_for("file_manager", uid=uid, proj=proj, token=token, path=relpath)
        )

    base, full = _safe_join_project(uid, proj, relpath)
    target = os.path.join(full, name)
    if not os.path.exists(target):
        with open(target, "w", encoding="utf-8") as f:
            f.write("")

    return redirect(
        url_for("file_manager", uid=uid, proj=proj, token=token, path=relpath)
    )


@app.route("/fm/delete", methods=["POST"])
def fm_delete():
    uid = request.form.get("uid")
    proj = request.form.get("proj")
    token = request.form.get("token", "")
    relpath = request.form.get("path", "")

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    import shutil

    base, full = _safe_join_project(uid, proj, relpath)
    if os.path.isdir(full):
        shutil.rmtree(full, ignore_errors=True)
    elif os.path.isfile(full):
        os.remove(full)

    parent = os.path.dirname(relpath)
    return redirect(
        url_for("file_manager", uid=uid, proj=proj, token=token, path=parent)
    )


@app.route("/fm/rename", methods=["POST"])
def fm_rename():
    uid = request.form.get("uid")
    proj = request.form.get("proj")
    token = request.form.get("token", "")
    old_rel = request.form.get("old_path", "")
    new_name = request.form.get("new_name", "").strip()

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    if not new_name:
        parent = os.path.dirname(old_rel)
        return redirect(
            url_for("file_manager", uid=uid, proj=proj, token=token, path=parent)
        )

    base, old_full = _safe_join_project(uid, proj, old_rel)
    parent_dir = os.path.dirname(old_full)
    new_full = os.path.join(parent_dir, new_name)
    os.rename(old_full, new_full)

    parent_rel = os.path.relpath(parent_dir, base)
    if parent_rel == ".":
        parent_rel = ""
    return redirect(
        url_for("file_manager", uid=uid, proj=proj, token=token, path=parent_rel)
    )


@app.route("/fm/download", methods=["GET"])
def fm_download():
    uid = request.args.get("uid")
    proj = request.args.get("proj")
    token = request.args.get("token", "")
    relpath = request.args.get("path", "")

    if not uid or not proj or not _verify_token(uid, proj, token):
        return "Unauthorized", 403

    base, full = _safe_join_project(uid, proj, relpath)
    if not os.path.exists(full):
        abort(404)

    return send_file(
        full,
        as_attachment=True,
        download_name=os.path.basename(full),
    )
