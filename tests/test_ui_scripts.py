from pathlib import Path
import shutil
import subprocess

import pytest


def test_shipped_ui_async_races_and_selection_state():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed only for the DOM-shim UI regression test")
    script = Path(__file__).with_name("ui_races.cjs")
    result = subprocess.run([node,str(script)],capture_output=True,text=True,encoding="utf-8",timeout=10)
    assert result.returncode == 0, result.stderr
    assert '"privacy":true' in result.stdout and '"latestImport":true' in result.stdout
