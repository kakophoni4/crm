"""ORM models — import all entities so Alembic metadata is complete."""

from app.modules.db.models.audit_log_entry import AuditLogEntry
from app.modules.db.models.base import Base
from app.modules.db.models.bot import Bot
from app.modules.db.models.bot_event_inbox import BotEventInbox
from app.modules.db.models.bot_outbound_log import BotOutboundLog
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.chat_read_state import ChatReadState
from app.modules.db.models.chat_takeover import ChatTakeover
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_field_change import ContactFieldChange
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.contact_group_transfer import ContactGroupTransfer
from app.modules.db.models.department import Department
from app.modules.db.models.enums import (
    AuditAction,
    BotOutboundStatus,
    BotOwnerType,
    ChatStatus,
    ContactStatus,
    MessageDirection,
    MessageKind,
    StatusKind,
    TransferStatus,
    UserAvailability,
    UserPresence,
    UserRole,
    UserStatus,
)
from app.modules.db.models.group import Group
from app.modules.db.models.group_escalation_settings import GroupEscalationSettings
from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_comment import LeadComment
from app.modules.db.models.message_reply_audit import MessageReplyAudit
from app.modules.db.models.refresh_token import RefreshToken
from app.modules.db.models.status import Status
from app.modules.db.models.user import User
from app.modules.db.models.uploaded_file import UploadedFile

__all__ = [
    "AuditAction",
    "AuditLogEntry",
    "Base",
    "Bot",
    "BotEventInbox",
    "BotOutboundLog",
    "BotOutboundStatus",
    "BotOwnerType",
    "Chat",
    "ChatMessage",
    "ChatReadState",
    "ChatStatus",
    "ChatTakeover",
    "Contact",
    "ContactFieldChange",
    "ContactGroupAssignment",
    "ContactGroupTransfer",
    "ContactStatus",
    "Department",
    "Group",
    "GroupEscalationSettings",
    "Lead",
    "LeadComment",
    "MessageDirection",
    "MessageKind",
    "MessageReplyAudit",
    "RefreshToken",
    "Status",
    "StatusKind",
    "TransferStatus",
    "UploadedFile",
    "User",
    "UserAvailability",
    "UserDeletionRequest",
    "UserPresence",
    "UserRole",
    "UserStatus",
]
