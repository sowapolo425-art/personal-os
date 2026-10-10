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
                assert names == {"capture_record", "search_records", "read_record", "propose_record",
                                 "ingest_conversation", "list_conversations", "mark_conversation_processed",
                                 "propose_insight", "prepare_analysis", "list_extraction_sources", "mark_source_processed", "get_memory_changes"}
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
                intake = await session.call_tool("ingest_conversation", {"agent": "fictional-agent",
                    "conversation_id": "session-1", "title": "虚构历史", "messages": [
                        {"message_id": "m1", "role": "user", "content": "我希望学习绘画"}]})
                assert not intake.isError
                listed = await session.call_tool("list_conversations", {})
                assert not listed.isError and "fictional-agent" in str(listed.content)
                from personal_os.conversations import list_conversations
                conversation = list_conversations(Store(vault))[0]
                insight = await session.call_tool("propose_insight", {"title": "学习目标", "content": "学习绘画",
                    "reason": "用户表达", "claim_type": "user_statement", "source_ids": conversation["record_ids"], "kind": "goal"})
                assert not insight.isError and Store(vault).search(kind="goal") == []
                pack = await session.call_tool("prepare_analysis", {"record_ids": conversation["record_ids"], "purpose": "分析学习目标"})
                assert not pack.isError and "personal-os-analysis" in str(pack.content)
                checkpoint = await session.call_tool("mark_conversation_processed", {"agent": "fictional-agent",
                    "conversation_id": "session-1", "fingerprint": conversation["fingerprint"]})
                assert not checkpoint.isError and list_conversations(Store(vault))[0]["state"] == "processed"
                materials = await session.call_tool("list_extraction_sources", {})
                assert not materials.isError and "虚构演示" in str(materials.content)
                from personal_os.conversations import list_sources
                material = list_sources(Store(vault))[0]
                done = await session.call_tool("mark_source_processed", {"record_id": material["id"], "fingerprint": material["fingerprint"]})
                assert not done.isError
                assert "list_extraction_sources" in str((await session.get_prompt("extract_materials")).messages)
                denied = await session.call_tool("read_record", {"record_id": "../escape"})
                assert denied.isError
                assert str((await session.list_resources()).resources[0].uri) == "personal-os://protocol"
                assert {p.name for p in (await session.list_prompts()).prompts} == {"personal_review", "extract_history", "extract_materials"}
                assert "ingest_conversation" in str((await session.get_prompt("extract_history")).messages)
                feed = await session.call_tool("get_memory_changes", {})
                assert not feed.isError and "cursor" in str(feed.content)
                expired = await session.call_tool("capture_record", {"title":"过期预算", "content":"虚构",
                    "memory":{"scope":"去年预算","valid_until":"2000-01-01T00:00:00Z"}})
                assert not expired.isError
                assert "过期预算" not in str((await session.call_tool("search_records", {})).content)
                Store(vault).delete(record["id"],record["revision"])
                assert (await session.call_tool("read_record", {"record_id":pending["record"]["id"]})).isError
                assert "evidence_invalidated" in str((await session.call_tool("get_memory_changes", {})).content)
    asyncio.run(asyncio.wait_for(run(), timeout=40))


def test_two_stdio_clients_keep_independent_restricted_permissions(tmp_path):
    vault = tmp_path / "多客户端资料"
    store = Store(vault)
    store.init()
    secret = store.capture("FICTIONAL_SECRET_TITLE", "FICTIONAL_SECRET_BODY", sensitivity="restricted")

    async def run():
        args = ["-m","personal_os.cli","--vault",str(vault),"serve"]
        default = StdioServerParameters(command=sys.executable,args=args)
        privileged = StdioServerParameters(command=sys.executable,args=[*args,"--allow-restricted"])
        async with stdio_client(default) as (r1,w1), stdio_client(privileged) as (r2,w2):
            async with ClientSession(r1,w1) as normal, ClientSession(r2,w2) as allowed:
                await normal.initialize()
                await allowed.initialize()
                hidden = await normal.call_tool("list_extraction_sources",{})
                assert "FICTIONAL_SECRET" not in str(hidden.content)
                denied = await normal.call_tool("prepare_analysis",{"record_ids":[secret["id"]],"purpose":"test"})
                assert denied.isError
                pack = await allowed.call_tool("prepare_analysis",{"record_ids":[secret["id"]],"purpose":"test"})
                assert not pack.isError and "FICTIONAL_SECRET_BODY" in str(pack.content)
                draft = await allowed.call_tool("propose_insight",{"title":"受限派生结论","content":"虚构分析",
                    "reason":"受限证据","source_ids":[secret["id"]],"claim_type":"inference"})
                assert not draft.isError and store.proposals()[0]["record"]["sensitivity"] == "restricted"
                intake = await allowed.call_tool("ingest_conversation",{"agent":"fictional-restricted",
                    "conversation_id":"c","title":"受限会话","sensitivity":"restricted",
                    "messages":[{"message_id":"1","role":"user","content":"虚构受限原文"}]})
                assert not intake.isError
                assert "fictional-restricted" not in str((await normal.call_tool("list_conversations",{})).content)
                assert "fictional-restricted" in str((await allowed.call_tool("list_conversations",{})).content)
    asyncio.run(asyncio.wait_for(run(),timeout=40))
