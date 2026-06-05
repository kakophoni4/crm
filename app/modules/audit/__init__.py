"""Global audit log and route decorators."""

from app.modules.audit.decorator import AuditedResult, audit
from app.modules.audit.service import AuditService

__all__ = ["AuditService", "AuditedResult", "audit"]
