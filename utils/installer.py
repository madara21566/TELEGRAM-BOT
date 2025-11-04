import re, subprocess, sys, shutil
from pathlib import Path

# Expanded list of common stdlib modules to avoid accidental pip install
STD_LIBS = {
    'os','sys','re','time','json','pathlib','subprocess','datetime','typing','itertools','math',
    'random','logging','threading','asyncio','http','urllib','collections','functools','heapq',
    'inspect','types','dataclasses','atexit','signal','shutil','glob','stat','enum','pathlib2'
}

def detect_imports_from_file(path):
    try:
        text = Path(path).read_text(errors='ignore')
    except Exception:
        return []
    pkgs = re.findall(r'^\s*(?:from|import)\s+([A-Za-z0-9_\.]+)', text, flags=re.M)
    pkgs = [p.split('.')[0] for p in pkgs if p]
    # filter out stdlib and builtins
    pkgs = [p for p in dict.fromkeys(pkgs) if p not in STD_LIBS and not p.isdigit()]
    return pkgs

def detect_imports_and_install(main_py_path):
    pkgs = detect_imports_from_file(main_py_path)
    if not pkgs:
        return []
    return safe_install_packages(pkgs)

def safe_install_packages(pkgs):
    if not pkgs: return []
    to_install = []
    for p in pkgs:
        # skip obviously invalid names
        if len(p) < 2 or any(c in p for c in ' /\\:') or p.lower() in STD_LIBS:
            continue
        to_install.append(p)
    if not to_install:
        return []
    try:
        # try install via pip, ignore failures per-package
        for pkg in to_install:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg], timeout=900)
            except Exception:
                # ignore install failure but continue with others
                pass
    except Exception:
        pass
    return to_install

def install_requirements_if_present(project_folder):
    req = Path(project_folder) / "requirements.txt"
    if req.exists():
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req)], timeout=900)
        except Exception:
            pass
        return True
    return False
