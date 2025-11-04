import json
from pathlib import Path
def load_json(p, default=None):
    p = Path(p)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except:
            return default if default is not None else {}
    return default if default is not None else {}
def save_json(p,d):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(d,indent=2),encoding='utf-8')
def ensure_state_user(uid):
    st = load_json('data/state.json',{})
    st.setdefault('users',{}).setdefault(str(uid),{}).setdefault('projects',[])
    save_json('data/state.json',st)
