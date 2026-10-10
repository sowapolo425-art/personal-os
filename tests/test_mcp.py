import asyncio
import sys
import subprocess
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from personal_os.store import Store


def test_real_stdio_mcp_roundtrip(tmp_path):
    vault = tmp_path / "用户资料 with spaces"
    Store(vault).init()

    async def run():
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "personal_os.cli", "--vault", str(vault), "serve"])
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert names == {"capture_record", "search_records", "read_record", "propose_record"}
                saved = await session.call_tool("capture_record", {"title": "虚构演示", "content": "练习复盘", "kind": "thought"})
                assert not saved.isError
                result = await session.call_tool("search_records", {"query": "复盘"})
                assert not result.isError and "虚构演示" in str(result.content)
                record = Store(vault).search()[0]
                read = await session.call_tool("read_record", {"record_id": record["id"]})
                assert not read.isError and "练习复盘" in str(read.content)
                proposal = await session.call_tool("propose_record", {"title": "认知草稿", "content": "喜欢复盘（待确认）", "reason": "单条演示记录", "source_ids": [record["id"]]})
                assert not proposal.isError
                assert Store(vault).search(kind="profile") == []
                pending = Store(vault).proposals()[0]
                approval = subprocess.run([sys.executable, "-m", "personal_os.cli", "--vault", str(vault),
                    "approve", pending["id"]], capture_output=True, text=True, encoding="utf-8")
                assert approval.returncode == 0, approval.stderr
                approved = await session.call_tool("read_record", {"record_id": pending["record"]["id"]})
                assert not approved.isError and "confirmed" in str(approved.content)
                denied = await session.call_tool("read_record", {"record_id": "../escape"})
                assert denied.isError
                assert str((await session.list_resources()).resources[0].uri) == "personal-os://protocol"
                assert (await session.list_prompts()).prompts[0].name == "personal_review"
    asyncio.run(asyncio.wait_for(run(), timeout=40))
