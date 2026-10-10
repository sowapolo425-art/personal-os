import json
from pathlib import Path
import subprocess
import sys

from personal_os.store import Store


def run(vault, *args, success=True):
    result = subprocess.run([sys.executable,"-m","personal_os.cli","--vault",str(vault),*args],
                            capture_output=True,text=True,encoding="utf-8",timeout=15)
    assert (result.returncode == 0) == success, result.stderr
    return json.loads(result.stdout) if success else result.stderr


def test_complete_cli_review_delete_restore_and_backup_workflow(tmp_path):
    vault = tmp_path / "用户资料 with spaces"
    assert run(vault,"init")["initialized"]
    assert run(vault,"init")["initialized"]
    store = Store(vault)
    source = store.capture("虚构原文","希望每月读一本书")
    proposal = store.propose("虚构目标","每月读一本书","根据原文",kind="goal",source_ids=[source["id"]])
    assert run(vault,"proposals")[0]["state"] == "pending"
    assert run(vault,"show-proposal",proposal["proposal_id"])["record"]["source_ids"] == [source["id"]]
    assert run(vault,"approve",proposal["proposal_id"])["state"] == "approved"
    assert "already reviewed" in run(vault,"approve",proposal["proposal_id"],success=False)
    rejected = store.propose("虚构其他目标","暂不确定","没有足够依据")
    assert run(vault,"reject",rejected["proposal_id"])["state"] == "rejected"
    assert "conflict" in run(vault,"delete",source["id"],"--revision","2",success=False)
    assert run(vault,"delete",source["id"],"--revision","1")["history_retained"]
    assert run(vault,"restore",source["id"],"--revision","1")["revision"] == 2
    backup = tmp_path / "backup.zip"
    assert run(vault,"backup","--output",str(backup))["encrypted"] is False
    assert run(vault,"backup","--output",str(backup),success=False)
    restored = run(vault,"restore-backup",str(backup))
    restored_store = Store(restored["restored_vault"])
    assert restored_store.get(source["id"])["content"] == source["content"]
    assert len(restored_store.proposals()) == 2
    assert store.get(source["id"])["revision"] == 2
    assert "outside" in run(vault,"backup","--output",str(vault/"bad.zip"),success=False)
    assert "outside" in run(vault,"analysis-pack","--ids",source["id"],"--purpose","分析", "--output",str(vault/"bad.json"),success=False)
    assert run(vault,"show-proposal","0"*32,success=False)


def test_dashboard_ports_and_missing_vault_errors(tmp_path):
    missing = tmp_path / "missing"
    assert "init" in run(missing,"dashboard","--no-browser",success=False)
    vault = tmp_path / "vault"
    Store(vault).init()
    for port in ("-1","65536"):
        assert "port" in run(vault,"dashboard","--port",port,"--no-browser",success=False)
