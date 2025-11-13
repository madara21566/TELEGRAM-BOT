import subprocess, re, os, sys

def run_cmd(cmd):
    """
    Run a shell command and return whether it succeeded.
    """
    try:
        result = subprocess.run(
            cmd, shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------- REQUIREMENTS INSTALLER ---------------- #

def install_requirements_if_present(base):
    """
    Install packages from requirements.txt if present.
    """
    req = os.path.join(base, "requirements.txt")
    if not os.path.exists(req):
        return False

    print("[Installer] Installing from requirements.txt...")

    try:
        subprocess.check_call(
            f"{sys.executable} -m pip install -r {req}",
            shell=True
        )
        return True
    except Exception as e:
        print("[Installer] Error installing requirements:", e)
        return False


# ---------------- IMPORT DETECTOR ---------------- #

IMPORT_REGEX = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", re.MULTILINE)

def detect_imports_and_install(pyfile):
    """
    Detect import statements inside .py and pip install missing modules.
    """
    if not os.path.exists(pyfile):
        print("[Installer] No python entry found.")
        return

    try:
        txt = open(pyfile, "r", encoding="utf-8", errors="ignore").read()
    except:
        return

    modules = set(re.findall(IMPORT_REGEX, txt))
    if not modules:
        return

    print("[Installer] Auto-installing detected imports:", modules)

    for mod in modules:
        pkg = mod.split(".")[0]  # top-level module

        # Skip built-in modules
        if pkg in ("os", "sys", "time", "json", "subprocess",
                   "signal", "asyncio", "datetime", "logging"):
            continue

        # Try installing
        try:
            subprocess.check_call(
                f"{sys.executable} -m pip install {pkg}",
                shell=True
            )
            print(f"[Installer] Installed {pkg}")
        except Exception as e:
            print(f"[Installer] Failed to install {pkg}:", e)
