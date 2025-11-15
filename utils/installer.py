import re, subprocess, sys, os

def install_requirements_if_present(base_path):
    req = os.path.join(base_path, "requirements.txt")
    if os.path.exists(req):
        subprocess.call([
            sys.executable, "-m", "pip", "install",
            "--no-cache-dir", "--prefer-binary", "-r", req
        ])

def detect_imports(py_path):
    try:
        code = open(py_path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return []
    imports = re.findall(
        r'^\\s*(?:from\\s+([\\w\\.]+)|import\\s+([\\w\\.]+))',
        code, flags=re.M
    )
    pkgs = set()
    for a, b in imports:
        mod = (a or b).split(".")[0]
        if mod in {"os", "sys", "time", "json", "re", "asyncio",
                   "logging", "subprocess", "typing", "datetime"}:
            continue
        if len(mod) < 2:
            continue
        pkgs.add(mod)
    return sorted(pkgs)

def safe_install_packages(pkgs):
    if not pkgs:
        return
    subprocess.call([
        sys.executable, "-m", "pip", "install",
        "--no-cache-dir", "--prefer-binary", *pkgs
    ])

def detect_imports_and_install(py_path):
    pkgs = detect_imports(py_path)
    safe_install_packages(pkgs)
    return pkgs
