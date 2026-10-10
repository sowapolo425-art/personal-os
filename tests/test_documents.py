import io
import json
import zipfile

import pytest
from pypdf import PdfWriter
from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject

from personal_os.documents import parse_document
from personal_os.importer import parse_import, preview_import, commit_import
from personal_os.store import Store
from personal_os.conversations import list_sources, mark_source_processed


def docx(text="Fictional project plan"):
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:body></w:document>')
    return memory.getvalue()


def pdf(blank=False, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if not blank:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 50 750 Td (Fictional reading plan) Tj ET")
        page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("fictional-password")
    memory = io.BytesIO()
    writer.write(memory)
    return memory.getvalue()


def test_pdf_and_docx_text_only_preview():
    assert "Fictional reading plan" in parse_document("plan.pdf", pdf())[0]["content"]
    item = parse_document("plan.docx", docx("虚构项目计划"))[0]
    assert item["content"] == "虚构项目计划" and item["filename"] == "plan.docx"
    assert parse_document("long.docx", docx("x" * 100_010))[1]["content"] == "x" * 10


@pytest.mark.parametrize("filename,data", [("../plan.pdf", pdf()), ("empty.pdf", pdf(blank=True)),
    ("secret.pdf", pdf(encrypted=True)), ("bad.pdf", b"invalid"), ("bad.docx", b"invalid"),
    ("large.docx", docx("x" * (8 * 1024 * 1024 + 1))), ("run.exe", b"program")],
    ids=["path", "scan", "encrypted", "invalid-pdf", "invalid-docx", "expanded-limit", "unsupported"])
def test_invalid_unsupported_documents_rejected(filename, data):
    with pytest.raises(ValueError):
        parse_document(filename, data)


def test_upload_and_daily_materials_have_progress_without_promotion(tmp_path):
    store = Store(tmp_path / "vault")
    store.init()
    items = parse_document("plan.docx", docx())
    result = commit_import(store, items, [items[0]["key"]], "private")
    thought = store.capture("虚构想法", "希望把项目做完", "thought")
    event = store.capture("虚构事务", "周五讨论项目", "event")
    secret = store.capture("私密", "不能默认提供", sensitivity="restricted")
    rows = list_sources(store)
    assert {r["id"] for r in rows} == {result["record_ids"][0], thought["id"], event["id"]}
    assert secret["id"] not in {r["id"] for r in rows}
    source = next(r for r in rows if r["id"] == thought["id"])
    mark_source_processed(store, thought["id"], source["fingerprint"])
    assert next(r for r in list_sources(store) if r["id"] == thought["id"])["state"] == "processed"
    assert store.search(kind="profile") == []
    store.restore(thought["id"], 1)
    with pytest.raises(ValueError, match="changed"):
        mark_source_processed(store, thought["id"], source["fingerprint"])
    with pytest.raises(ValueError, match="Restricted"):
        mark_source_processed(store, secret["id"], "bad")


def test_same_text_from_different_files_preserves_sources(tmp_path):
    store = Store(tmp_path / "vault")
    store.init()
    first = parse_import("a.txt", "相同文字不同来源")
    second = parse_import("b.txt", "相同文字不同来源")
    assert commit_import(store, first, [first[0]["key"]], "private")["imported"] == 1
    assert preview_import(store, first)[0]["duplicate"]
    assert not preview_import(store, second)[0]["duplicate"]
    assert commit_import(store, second, [second[0]["key"]], "private")["imported"] == 1
    assert {r["source"] for r in store.search()} == {"local import / a.txt", "local import / b.txt"}
