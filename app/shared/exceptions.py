from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.request_id import generate_ulid, get_request_id
from app.shared.sentry import capture_exception


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status = status
        self.details = details
        super().__init__(message)


class ValidationError(AppError):
    def __init__(
        self,
        message: str = "Validation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="validation_error",
            message=message,
            status=422,
            details=details,
        )


class AuthenticationRequired(AppError):
    def __init__(
        self,
        message: str = "Authentication required",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="authentication_required",
            message=message,
            status=401,
            details=details,
        )


class PermissionDenied(AppError):
    def __init__(
        self,
        message: str = "Permission denied",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="permission_denied",
            message=message,
            status=403,
            details=details,
        )


class NotFound(AppError):
    def __init__(
        self,
        message: str = "Resource not found",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="not_found",
            message=message,
            status=404,
            details=details,
        )


class Conflict(AppError):
    def __init__(
        self,
        message: str = "Conflict",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="conflict",
            message=message,
            status=409,
            details=details,
        )


class RateLimited(AppError):
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="rate_limited",
            message=message,
            status=429,
            details=details,
        )


class Gone(AppError):
    def __init__(
        self,
        message: str = "Resource is no longer available",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="gone",
            message=message,
            status=410,
            details=details,
        )


def _resolve_request_id() -> str:
    return get_request_id() or generate_ulid()


def error_payload(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id or _resolve_request_id(),
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def _json_safe_validation_error(err: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in err.items():
        if key == "ctx" and isinstance(value, dict):
            safe[key] = {
                ctx_key: str(ctx_val) if isinstance(ctx_val, BaseException) else ctx_val
                for ctx_key, ctx_val in value.items()
            }
        elif isinstance(value, BaseException):
            safe[key] = str(value)
        else:
            safe[key] = value
    return safe


def _format_validation_errors(exc: RequestValidationError) -> tuple[str, dict[str, Any]]:
    errors = [_json_safe_validation_error(item) for item in exc.errors()]
    if not errors:
        return "Validation failed", {}
    first = errors[0]
    loc = first.get("loc", ())
    field_parts = [str(part) for part in loc if part not in ("body", "query", "path")]
    field = ".".join(field_parts) if field_parts else "request"
    message = first.get("msg", "Validation failed")
    if field:
        message = f"Field '{field}' is invalid: {message}"
    return message, {"field": field, "errors": errors}


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content=error_payload(exc.code, exc.message, exc.details),
    )


async def validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    message, details = _format_validation_errors(exc)
    return JSONResponse(
        status_code=422,
        content=error_payload("validation_error", message, details),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    capture_exception(exc)
    return JSONResponse(
        status_code=500,
        content=error_payload(
            "internal_error",
            "Internal server error",
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
