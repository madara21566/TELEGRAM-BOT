import zipfile, time, os, shutil
from pathlib import Path

def create_backup_and_rotate(users_dir, backups_dir, max_keep=5):
    users_dir = Path(users_dir); backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True,exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = backups_dir / f"backup_{ts}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in users_dir.rglob("*"):
            try:
                z.write(str(p), str(p.relative_to(users_dir.parent)))
            except Exception:
                pass
    files = sorted(backups_dir.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max_keep:]:
        try: old.unlink()
        except: pass
    return out
