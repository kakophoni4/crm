from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

import httpx

from app.shared.settings import Settings, get_settings


def _sign_aws4(
    *,
    method: str,
    bucket: str,
    key: str,
    payload_hash: str,
    access_key: str,
    secret_key: str,
    region: str,
    endpoint: str,
    content_type: str | None = None,
) -> dict[str, str]:
    parsed = urlparse(endpoint)
    host = parsed.netloc
    amz_date = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    date_stamp = amz_date[:8]
    canonical_uri = f"/{bucket}/{quote(key, safe='/')}"
    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = (
        f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = (
        "AWS4-HMAC-SHA256\n"
        f"{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _sign(f"AWS4{secret_key}".encode(), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, "s3")
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    headers = {
        "Authorization": authorization,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "Host": host,
    }
    if content_type is not None:
        headers["Content-Type"] = content_type
    return headers


_EMPTY_PAYLOAD_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _object_url(settings: Settings, key: str) -> str:
    base = settings.s3_endpoint.rstrip("/")
    bucket = settings.s3_bucket_files
    return f"{base}/{bucket}/{quote(key, safe='/')}"


class FileStorage:
    async def upload_bytes(self, key: str, data: bytes, content_type: str) -> str:
        settings = get_settings()
        payload_hash = hashlib.sha256(data).hexdigest()
        headers = _sign_aws4(
            method="PUT",
            bucket=settings.s3_bucket_files,
            key=key,
            payload_hash=payload_hash,
            content_type=content_type,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            endpoint=settings.s3_endpoint,
        )
        url = _object_url(settings, key)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.put(url, content=data, headers=headers)
            response.raise_for_status()
        return url

    async def get_bytes(self, key: str) -> tuple[bytes, str]:
        settings = get_settings()
        headers = _sign_aws4(
            method="GET",
            bucket=settings.s3_bucket_files,
            key=key,
            payload_hash=_EMPTY_PAYLOAD_HASH,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            endpoint=settings.s3_endpoint,
        )
        url = _object_url(settings, key)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "application/octet-stream")
            return response.content, str(content_type)

    async def presign_get(self, key: str, expires: int = 3600) -> str:
        settings = get_settings()
        # Internal URL only — browsers must use /api/v1/chats/.../attachments/{idx}.
        return f"{_object_url(settings, key)}?expires={expires}"


_storage: FileStorage | None = None


def get_file_storage() -> FileStorage:
    global _storage
    if _storage is None:
        _storage = FileStorage()
    return _storage


def set_file_storage(storage: FileStorage) -> None:
    global _storage
    _storage = storage
