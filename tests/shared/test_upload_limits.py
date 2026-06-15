from app.shared.upload_limits import is_photo_attachment, max_upload_bytes_for

PHOTO = 10 * 1024 * 1024
FILE = 50 * 1024 * 1024


def test_photo_by_mime() -> None:
    assert max_upload_bytes_for(
        mime="image/png",
        max_photo_bytes=PHOTO,
        max_file_bytes=FILE,
    ) == PHOTO


def test_file_by_mime() -> None:
    assert max_upload_bytes_for(
        mime="application/pdf",
        max_photo_bytes=PHOTO,
        max_file_bytes=FILE,
    ) == FILE


def test_photo_by_attachment_type() -> None:
    assert is_photo_attachment(att_type="photo", mime=None)
    assert max_upload_bytes_for(
        mime=None,
        att_type="photo",
        max_photo_bytes=PHOTO,
        max_file_bytes=FILE,
    ) == PHOTO
