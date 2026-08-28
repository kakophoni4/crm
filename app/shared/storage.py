from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from urllib.parse import quote, urlencode, urlparse
from xml.sax.saxutils import escape as xml_escape

import httpx

from app.shared.settings import Settings, get_settings

_EMPTY_PAYLOAD_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_UPLOAD_ID_RE = re.compile(r"<UploadId>([^<]+)</UploadId>")


def canonical_query_string(query: Mapping[str, str] | None) -> str:
    if not query:
        return ""
    return urlencode(sorted(query.items()), quote_via=quote, safe="-_.~")


def complete_multipart_xml(parts: list[tuple[int, str]]) -> str:
    body = "".join(
        (
            "<Part>"
            f"<PartNumber>{number}</PartNumber>"
            f"<ETag>{xml_escape(etag)}</ETag>"
            "</Part>"
        )
        for number, etag in parts
    )
    return f"<CompleteMultipartUpload>{body}</CompleteMultipartUpload>"


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
    query: Mapping[str, str] | None = None,
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
        f"{method}\n{canonical_uri}\n{canonical_query_string(query)}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = (
        "AWS4-HMAC-SHA256\n"
        f"{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    def _sign(key_bytes: bytes, msg: str) -> bytes:
        return hmac.new(key_bytes, msg.encode(), hashlib.sha256).digest()

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


def _object_url(settings: Settings, key: str, query: Mapping[str, str] | None = None) -> str:
    base = settings.s3_endpoint.rstrip("/")
    bucket = settings.s3_bucket_files
    url = f"{base}/{bucket}/{quote(key, safe='/')}"
    qs = canonical_query_string(query)
    if qs:
        return f"{url}?{qs}"
    return url


def _s3_timeout(*, read: float | None = 60.0, write: float = 60.0) -> httpx.Timeout:
    return httpx.Timeout(connect=30.0, read=read, write=write, pool=30.0)


class FileStorage:
    def _auth_headers(
        self,
        *,
        method: str,
        key: str,
        payload_hash: str,
        content_type: str | None = None,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        settings = get_settings()
        return _sign_aws4(
            method=method,
            bucket=settings.s3_bucket_files,
            key=key,
            payload_hash=payload_hash,
            content_type=content_type,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            endpoint=settings.s3_endpoint,
            query=query,
        )

    async def upload_bytes(self, key: str, data: bytes, content_type: str) -> str:
        settings = get_settings()
        payload_hash = hashlib.sha256(data).hexdigest()
        headers = self._auth_headers(
            method="PUT",
            key=key,
            payload_hash=payload_hash,
            content_type=content_type,
        )
        url = _object_url(settings, key)
        async with httpx.AsyncClient(timeout=_s3_timeout()) as client:
            response = await client.put(url, content=data, headers=headers)
            response.raise_for_status()
        return url

    async def get_bytes(self, key: str) -> tuple[bytes, str]:
        settings = get_settings()
        headers = self._auth_headers(
            method="GET",
            key=key,
            payload_hash=_EMPTY_PAYLOAD_HASH,
        )
        url = _object_url(settings, key)
        async with httpx.AsyncClient(timeout=_s3_timeout(read=120.0)) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "application/octet-stream")
            return response.content, str(content_type)

    async def iter_object_bytes(self, key: str, *, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        settings = get_settings()
        headers = self._auth_headers(
            method="GET",
            key=key,
            payload_hash=_EMPTY_PAYLOAD_HASH,
        )
        url = _object_url(settings, key)
        timeout = _s3_timeout(read=None, write=120.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size):
                    if chunk:
                        yield chunk

    async def presign_get(self, key: str, expires: int = 3600) -> str:
        settings = get_settings()
        # Internal URL only — browsers must use /api/v1/chats/.../attachments/{idx}.
        return f"{_object_url(settings, key)}?expires={expires}"

    async def delete_object(self, key: str) -> None:
        settings = get_settings()
        headers = self._auth_headers(
            method="DELETE",
            key=key,
            payload_hash=_EMPTY_PAYLOAD_HASH,
        )
        url = _object_url(settings, key)
        async with httpx.AsyncClient(timeout=_s3_timeout()) as client:
            response = await client.delete(url, headers=headers)
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()

    async def initiate_multipart(self, key: str, content_type: str) -> str:
        settings = get_settings()
        query = {"uploads": ""}
        headers = self._auth_headers(
            method="POST",
            key=key,
            payload_hash=_EMPTY_PAYLOAD_HASH,
            content_type=content_type,
            query=query,
        )
        url = _object_url(settings, key, query)
        async with httpx.AsyncClient(timeout=_s3_timeout()) as client:
            response = await client.post(url, content=b"", headers=headers)
            response.raise_for_status()
        match = _UPLOAD_ID_RE.search(response.text)
        if match is None:
            raise RuntimeError("S3 initiate multipart did not return UploadId")
        return match.group(1)

    async def upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> str:
        settings = get_settings()
        query = {"partNumber": str(part_number), "uploadId": upload_id}
        payload_hash = hashlib.sha256(data).hexdigest()
        headers = self._auth_headers(
            method="PUT",
            key=key,
            payload_hash=payload_hash,
            content_type="application/octet-stream",
            query=query,
        )
        url = _object_url(settings, key, query)
        async with httpx.AsyncClient(timeout=_s3_timeout(read=180.0, write=180.0)) as client:
            response = await client.put(url, content=data, headers=headers)
            response.raise_for_status()
        etag = response.headers.get("etag") or response.headers.get("ETag")
        if not etag:
            raise RuntimeError(f"S3 part {part_number} did not return ETag")
        return etag.strip()

    async def complete_multipart(
        self,
        key: str,
        upload_id: str,
        parts: list[tuple[int, str]],
    ) -> None:
        settings = get_settings()
        query = {"uploadId": upload_id}
        xml = complete_multipart_xml(parts)
        body = xml.encode("utf-8")
        payload_hash = hashlib.sha256(body).hexdigest()
        headers = self._auth_headers(
            method="POST",
            key=key,
            payload_hash=payload_hash,
            content_type="application/xml",
            query=query,
        )
        url = _object_url(settings, key, query)
        async with httpx.AsyncClient(timeout=_s3_timeout(read=180.0, write=180.0)) as client:
            response = await client.post(url, content=body, headers=headers)
            response.raise_for_status()

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        settings = get_settings()
        query = {"uploadId": upload_id}
        headers = self._auth_headers(
            method="DELETE",
            key=key,
            payload_hash=_EMPTY_PAYLOAD_HASH,
            query=query,
        )
        url = _object_url(settings, key, query)
        async with httpx.AsyncClient(timeout=_s3_timeout()) as client:
            response = await client.delete(url, headers=headers)
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()


_storage: FileStorage | None = None


def get_file_storage() -> FileStorage:
    global _storage
    if _storage is None:
        _storage = FileStorage()
    return _storage


def set_file_storage(storage: FileStorage) -> None:
    global _storage
    _storage = storage
