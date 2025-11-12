import os, shutil, time, zipfile

def backup_projects():
    base = "data"
    out_root = "data/backups"
    os.makedirs(out_root, exist_ok=True)
    ts = int(time.time())
    out = os.path.join(out_root, f"backup_{ts}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for r,d,fs in os.walk("data"):
            for f in fs:
                p = os.path.join(r,f)
                z.write(p, os.path.relpath(p, "data"))
    items = sorted([os.path.join(out_root,f) for f in os.listdir(out_root) if f.endswith('.zip')], key=os.path.getmtime, reverse=True)
    for old in items[3:]:
        try: os.remove(old)
        except: pass
    return out
