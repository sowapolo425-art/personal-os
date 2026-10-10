"""Bootstrap a private local installation, then start the dashboard."""
import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path


def select_vault():
    try:
        from tkinter import Tk, filedialog
        window = Tk()
        window.withdraw()
        window.attributes("-topmost", True)
        selection = filedialog.askdirectory(title="Personal OS：选择或新建你的个人资料库文件夹")
        window.destroy()
        return selection
    except Exception:
        if sys.stdin.isatty():
            return input("Personal OS vault folder (absolute path): ").strip()
        return ""


def load_preferences(path):
    if not path.exists():
        return {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or not isinstance(saved.get("vault"), str) or not saved["vault"].strip():
            raise ValueError("Invalid saved vault")
        if not Path(saved["vault"]).expanduser().is_dir():
            raise ValueError("Saved vault no longer exists")
        return saved
    except (ValueError, OSError):
        print("Saved folder preference is unavailable. Please choose your vault again.", flush=True)
        return {}


def main():
    parser = argparse.ArgumentParser(description="Set up and launch Personal OS locally")
    parser.add_argument("--vault", help="Use this folder instead of opening the folder selector")
    parser.add_argument("--choose", action="store_true", help="Choose another vault")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ is required.")
    root = Path(__file__).resolve().parents[1]
    preferences = root / ".local" / "launcher.json"
    saved = {} if args.vault or args.choose else load_preferences(preferences)
    chosen = args.vault or (None if args.choose else saved.get("vault")) or select_vault()
    if not chosen:
        print("Cancelled. No vault was created.")
        return
    vault = Path(chosen).expanduser().resolve()
    if vault == root or root.is_relative_to(vault) or vault.is_relative_to(root):
        raise SystemExit("Choose a private data folder outside the project directory.")
    environment = root / ".venv"
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.exists():
        print("Setting up Python environment; first launch requires internet.", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    stamp = environment / "personal-os.version"
    if not stamp.exists() or stamp.read_text(encoding="utf-8") != version:
        subprocess.run([str(executable), "-m", "pip", "install", "-e", str(root)], check=True)
        stamp.write_text(version, encoding="utf-8")
    subprocess.run([str(executable), "-m", "personal_os.cli", "--vault", str(vault), "init"], check=True)
    preferences.parent.mkdir(exist_ok=True)
    preferences.write_text(json.dumps({"vault": str(vault)}, ensure_ascii=False), encoding="utf-8")
    if args.prepare_only:
        print("Ready. Launch again to open the local dashboard.")
        return
    command = [str(executable), "-m", "personal_os.cli", "--vault", str(vault), "dashboard", "--port", "0"]
    if args.no_browser:
        command.append("--no-browser")
    subprocess.run(command, check=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Personal OS setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
