from __future__ import annotations

from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM


class UserRole(StrEnum):
    USER = "user"
    SENIOR = "senior"
    GROUP_SENIOR = "group_senior"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    CHIEF_ACCOUNTANT = "chief_accountant"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class UserDeletionRequestState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class UserPresence(StrEnum):
    ONLINE = "online"
    AWAY = "away"
    BUSY = "busy"
    OFFLINE = "offline"


class UserAvailability(StrEnum):
    AVAILABLE = "available"
    DO_NOT_ASSIGN = "do_not_assign"


class ContactStatus(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    RETURNING = "returning"
    DISABLED = "disabled"
    MERGED = "merged"
    ARCHIVED = "archived"


class ChatStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    ARCHIVED = "archived"


class StatusKind(StrEnum):
    LEAD_PIPELINE = "lead_pipeline"
    CHAT_LABEL = "chat_label"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    DOCUMENT = "document"
    SYSTEM = "system"


class BotChannel(StrEnum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    BITCALL = "bitcall"


class BotOwnerType(StrEnum):
    DEPARTMENT = "department"
    GROUP = "group"


class BotOutboundStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class TransferStatus(StrEnum):
    PENDING_SENIOR = "pending_senior"
    PENDING_RECIPIENT = "pending_recipient"
    APPROVED = "approved"
    ACCEPTED = "accepted"
    DECLINED_SENIOR = "declined_senior"
    DECLINED_RECIPIENT = "declined_recipient"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


CONTACT_TRANSFER_ACTIVE_STATES: frozenset[TransferStatus] = frozenset(
    {
        TransferStatus.PENDING_SENIOR,
        TransferStatus.PENDING_RECIPIENT,
        TransferStatus.APPROVED,
    },
)


class AuditAction(StrEnum):
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_FORCE_LOGOUT = "auth.force_logout"
    DEPARTMENT_CREATE = "department.create"
    DEPARTMENT_UPDATE = "department.update"
    DEPARTMENT_DELETE = "department.delete"
    GROUP_CREATE = "group.create"
    GROUP_UPDATE = "group.update"
    GROUP_DELETE = "group.delete"
    CHAT_CREATE = "chat.create"
    CHAT_STATUS_UPDATE = "chat.status.update"
    CHAT_ARCHIVE = "chat.archive"
    CHAT_MESSAGE_SEND = "chat.message.send"
    CHAT_TRANSFER_REQUEST = "chat.transfer.request"
    CHAT_TRANSFER_APPROVE = "chat.transfer.approve"
    CHAT_TRANSFER_DECLINE = "chat.transfer.decline"
    CHAT_TRANSFER_ACCEPT = "chat.transfer.accept"
    CHAT_TRANSFER_CANCEL = "chat.transfer.cancel"
    CHAT_TRANSFER_FORCE = "chat.transfer.force"
    CHAT_TAKEOVER = "chat.takeover"
    CHAT_TAKEOVER_RELEASE = "chat.takeover.release"
    CONTACT_CREATE = "contact.create"
    CONTACT_UPDATE = "contact.update"
    CONTACT_DELETE = "contact.delete"
    BOT_CREATE = "bot.create"
    BOT_UPDATE = "bot.update"
    LEAD_CREATE = "lead.create"
    LEAD_UPDATE = "lead.update"
    LEAD_CLOSE = "lead.close"
    LEAD_STATUS_UPDATE = "lead.status.update"


user_role_pg = ENUM(
    UserRole,
    name="user_role",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

user_status_pg = ENUM(
    UserStatus,
    name="user_status",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

user_presence_pg = ENUM(
    UserPresence,
    name="user_presence",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

user_availability_pg = ENUM(
    UserAvailability,
    name="user_availability",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

contact_status_pg = ENUM(
    ContactStatus,
    name="contact_status",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

audit_action_pg = ENUM(
    AuditAction,
    name="audit_action",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

chat_status_pg = ENUM(
    ChatStatus,
    name="chat_status",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

message_direction_pg = ENUM(
    MessageDirection,
    name="message_direction",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

message_kind_pg = ENUM(
    MessageKind,
    name="message_kind",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

transfer_status_pg = ENUM(
    TransferStatus,
    name="transfer_status",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

bot_owner_type_pg = ENUM(
    BotOwnerType,
    name="bot_owner_type",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

bot_outbound_status_pg = ENUM(
    BotOutboundStatus,
    name="bot_outbound_status",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)
