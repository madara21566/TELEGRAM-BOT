import os, shutil, time, requests
from utils.helpers import load_json, save_json, STATE_FILE

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = os.getenv("OWNER_ID", "")

def _send_document_to_owner(path):
    if not BOT_TOKEN or not OWNER_ID: return
    try:
        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": OWNER_ID, "caption": "📦 Auto backup"},
                files={"document": (os.path.basename(path), f)}
            )
    except Exception:
        pass

def backup_projects_and_notify_owner():
    base = "data/users"; out_root = "data/backups"
    os.makedirs(out_root, exist_ok=True)
    made = []
    for uid in os.listdir(base):
        udir = os.path.join(base, uid)
        if not os.path.isdir(udir): continue
        for proj in os.listdir(udir):
            pdir = os.path.join(udir, proj)
            if not os.path.isdir(pdir): continue
            ts = int(time.time())
            outdir = os.path.join(out_root, uid)
            os.makedirs(outdir, exist_ok=True)
            out = os.path.join(outdir, f"{proj}_{ts}")
            shutil.make_archive(out, "zip", pdir)
            zip_path = f"{out}.zip"
            made.append(zip_path)
            _send_document_to_owner(zip_path)

    # Keep only last 3 per user
    for uid in os.listdir(out_root):
        uout = os.path.join(out_root, uid)
        if not os.path.isdir(uout): continue
        zips = sorted([f for f in os.listdir(uout) if f.endswith(".zip")], reverse=True)
        for old in zips[3:]:
            try: os.remove(os.path.join(uout, old))
            except Exception: pass

    # record last backup time
    if made:
        st = load_json()
        st["last_backup"] = int(time.time())
        save_json(STATE_FILE, st)
