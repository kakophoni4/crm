from app.modules.accounting.requirement_kinds import (
    DOC_KIND_ACCOUNT_BLOCK,
    is_account_block_notice,
)
from app.modules.accounting.sbis_norm_sync import map_meta_to_ingest


def test_detect_by_title() -> None:
    assert is_account_block_notice(title="Уведомление о блокировке счета")
    assert is_account_block_notice(title="Блокировка расчётного счёта")
    assert not is_account_block_notice(title="Требование ФНС", filename="req.pdf")


def test_detect_by_stub_filename() -> None:
    assert is_account_block_notice(title="Требование ФНС", filename="doc.stub")
    assert is_account_block_notice(metadata={"storage_file_name": "x.STUB"})


def test_detect_by_metadata_kind() -> None:
    assert is_account_block_notice(
        title="Требование ФНС",
        filename="req.pdf",
        metadata={"doc_kind": DOC_KIND_ACCOUNT_BLOCK},
    )


def test_empty_file_alone_is_not_enough() -> None:
    assert not is_account_block_notice(
        title="Требование СФР",
        filename="sfr.xml",
        metadata={"file_size": 0},
    )


def test_map_meta_notice_does_not_use_answered() -> None:
    body = map_meta_to_ingest(
        {
            "id": 7,
            "inn": "9731112362",
            "doc_title": "Уведомление о блокировке счета",
            "storage_file_name": "block.stub",
            "reply_status": "answered",
        },
        pdf_bytes=b"",
    )
    assert body.reply_status == "none"
    assert body.metadata["doc_kind"] == "account_block"
    assert body.metadata["can_reply"] is False
    assert body.title == "Уведомление о блокировке счета"
