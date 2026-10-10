import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "scripts" / "launch.py"
    root = tmp_path / "project"
    (root / "scripts").mkdir(parents=True)
    script = root / "scripts" / "launch.py"
    script.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nversion="test-version"\n', encoding="utf-8")
    executable = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test stub; never executed")
    (root / ".venv" / "personal-os.version").write_text("test-version", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("personal_os_test_launcher", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: calls.append(command))
    return module, root, calls


@pytest.mark.parametrize("raw", ["{broken", "[]", '{"vault":42}', '{"vault":"missing-path"}'])
def test_bad_preferences_recover_without_creating_a_vault(launcher, monkeypatch, raw):
    module, root, calls = launcher
    (root / ".local").mkdir()
    (root / ".local" / "launcher.json").write_text(raw, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["launch.py"])
    monkeypatch.setattr(module, "select_vault", lambda: "")
    module.main()
    assert not calls


def test_explicit_vault_ignores_bad_preferences_and_second_launch_reuses_it(launcher, monkeypatch, tmp_path):
    module, root, calls = launcher
    vault = tmp_path / "用户资料 with spaces"
    vault.mkdir()
    (root / ".local").mkdir()
    preferences = root / ".local" / "launcher.json"
    preferences.write_text("broken", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["launch.py", "--vault", str(vault), "--prepare-only"])
    module.main()
    assert len(calls) == 1 and calls[0][-1] == "init"
    assert json.loads(preferences.read_text(encoding="utf-8"))["vault"] == str(vault)
    calls.clear()
    monkeypatch.setattr(sys, "argv", ["launch.py", "--no-browser"])
    monkeypatch.setattr(module, "select_vault", lambda: pytest.fail("Existing vault should be reused"))
    module.main()
    assert len(calls) == 2 and calls[1][-1] == "--no-browser" and "0" in calls[1]


def test_choose_ignores_saved_path_and_inside_project_is_rejected(launcher, monkeypatch, tmp_path):
    module, root, calls = launcher
    old = tmp_path / "old"
    old.mkdir()
    (root / ".local").mkdir()
    (root / ".local" / "launcher.json").write_text(json.dumps({"vault":str(old)}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["launch.py", "--choose", "--prepare-only"])
    monkeypatch.setattr(module, "select_vault", lambda: str(root / "private-data"))
    with pytest.raises(SystemExit, match="outside"):
        module.main()
    assert calls == [] and not (root / "private-data").exists()


def test_version_change_installs_dependencies_before_init(launcher, monkeypatch, tmp_path):
    module, root, calls = launcher
    vault = tmp_path / "vault"
    vault.mkdir()
    (root / ".venv" / "personal-os.version").write_text("old-version", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["launch.py", "--vault", str(vault), "--prepare-only"])
    module.main()
    assert len(calls) == 2 and "pip" in calls[0] and calls[1][-1] == "init"
