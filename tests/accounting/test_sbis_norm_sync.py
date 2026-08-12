from app.modules.accounting.sbis_norm_sync import external_id_for_sbis, map_meta_to_ingest


def test_external_id_prefix() -> None:
    assert external_id_for_sbis(12) == "sbis-req:12"


def test_map_meta_to_ingest_with_pdf() -> None:
    pdf = b"%PDF-1.4 fake"
    detail = {
        "id": 42,
        "inn": "9707039440",
        "document_date": "2026-07-06",
        "sbis_doc_id": "abc-doc",
        "sbis_stage_id": "stage-1",
        "doc_title": "Требование ФНС",
        "content_sha256": "deadbeef",
        "storage_file_name": "req.pdf",
        "created_at": "2026-07-10T14:22:01.123456+00:00",
        "file_size": len(pdf),
    }
    body = map_meta_to_ingest(detail, pdf_bytes=pdf)
    assert body.external_id == "sbis-req:42"
    assert body.supplier_inn == "9707039440"
    assert body.title == "Требование ФНС"
    assert body.pdf_filename == "req.pdf"
    assert body.metadata["sbis_doc_id"] == "abc-doc"
    assert body.metadata["mime_type"] == "application/pdf"
    assert body.reply_status == "none"
    assert body.metadata.get("doc_kind") != "account_block"
