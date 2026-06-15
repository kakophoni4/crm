from __future__ import annotations


def is_photo_mime(mime: str | None) -> bool:
    return bool(mime and mime.lower().startswith("image/"))


def is_photo_attachment(*, att_type: str | None = None, mime: str | None = None) -> bool:
    if att_type == "photo":
        return True
    return is_photo_mime(mime)


def max_upload_bytes_for(
    *,
    mime: str | None,
    att_type: str | None = None,
    max_photo_bytes: int,
    max_file_bytes: int,
) -> int:
    if is_photo_attachment(att_type=att_type, mime=mime):
        return max_photo_bytes
    return max_file_bytes
