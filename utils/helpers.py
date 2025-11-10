import json, os

STATE_FILE = "data/state.json"

def load_json(path=STATE_FILE, default=None):
    if default is None: default = {}
    if not os.path.exists(path): return default
    try:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

def ensure_state_user(uid):
    st = load_json()
    suid = str(uid)
    st.setdefault("users",{}).setdefault(suid,{}).setdefault("projects",[])
    save_json(STATE_FILE, st)
    return st

def is_banned(uid):
    st = load_json()
    return str(uid) in st.get("banned", [])

def is_premium(uid):
    st = load_json()
    return str(uid) in st.get("premium_users", [])

def running_count(uid):
    st = load_json()
    return len(st.get("procs", {}).get(str(uid), {}))
