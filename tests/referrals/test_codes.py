from app.modules.referrals.codes import (
    build_referral_url,
    extract_ref_code,
    normalize_bot_username,
    normalize_ref_code,
)


def test_normalize_ref_code_from_start_command() -> None:
    assert normalize_ref_code("/start thshchbjvtsygivxy") == "thshchbjvtsygivxy"
    assert normalize_ref_code("/start@timeletterer_bot abc123") == "abc123"
    assert normalize_ref_code("  ") is None
    assert normalize_ref_code("???") is None


def test_extract_ref_code_prefers_contact_field() -> None:
    assert (
        extract_ref_code(
            {
                "contact": {"ref_code": "OwnerCode"},
                "message": {"text": "/start other"},
            },
        )
        == "ownercode"
    )
    assert extract_ref_code({"contact": {}, "message": {"text": "hello"}}) is None
    assert extract_ref_code({"contact": {"ref_code": ""}, "message": {"text": "hi"}}) is None


def test_build_referral_url() -> None:
    assert (
        build_referral_url("timeletterer_bot", "thshchbjvtsygivxy")
        == "https://t.me/timeletterer_bot?start=thshchbjvtsygivxy"
    )
    assert normalize_bot_username("@TimeLetterer_bot") == "TimeLetterer_bot"
