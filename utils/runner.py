import subprocess, sys, time, os, json
from pathlib import Path
from utils.helpers import load_json, save_json

STATE_FILE = "data/state.json"

def start_user_process(uid, project, filename):
    base = Path('data/users')/str(uid)/project
    script = base/filename
    if not script.exists(): raise FileNotFoundError('not found')
    venv = base/".venv"
    python_bin = sys.executable
    try:
        if not venv.exists():
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=False)
            if os.name != 'nt':
                python_bin = str(venv / "bin" / "python")
            else:
                python_bin = str(venv / "Scripts" / "python.exe")
    except Exception:
        python_bin = sys.executable
    req = base/ "requirements.txt"
    if req.exists():
        try:
            subprocess.run([python_bin, "-m", "pip", "install", "-r", str(req)], check=False, timeout=900)
        except Exception:
            pass
    out = base / (filename + ".out.log")
    err = base / (filename + ".err.log")
    fo = open(out, "ab"); fe = open(err, "ab")
    p = subprocess.Popen([python_bin, str(script)], cwd=str(base), stdout=fo, stderr=fe)
    st = load_json(STATE_FILE, {})
    procs = st.setdefault("procs", {})
    procs.setdefault(str(uid), {})[f"{project}:{filename}"] = {"pid": p.pid, "start": time.time()}
    save_json(STATE_FILE, st)
    return p.pid

def stop_user_process(uid, project, filename):
    st = load_json(STATE_FILE, {})
    entry = st.get("procs", {}).get(str(uid), {}).get(f"{project}:{filename}")
    if not entry:
        return False
    pid = entry.get("pid")
    try:
        import psutil
        p = psutil.Process(pid)
        p.terminate(); p.wait(timeout=5)
    except Exception:
        try:
            os.kill(pid, 9)
        except Exception:
            pass
    st.get("procs", {}).get(str(uid), {}).pop(f"{project}:{filename}", None)
    save_json(STATE_FILE, st)
    return True
