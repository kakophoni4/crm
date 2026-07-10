"""ORM models — import all entities so Alembic metadata is complete."""

from app.modules.db.models.audit_log_entry import AuditLogEntry
from app.modules.db.models.base import Base
from app.modules.db.models.bot import Bot
from app.modules.db.models.bot_event_inbox import BotEventInbox
from app.modules.db.models.bot_group_assignment import BotGroupAssignment
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.chat_read_state import ChatReadState
from app.modules.db.models.chat_takeover import ChatTakeover
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_field_change import ContactFieldChange
from app.modules.db.models.file_share_link import FileShareLink
from app.modules.db.models.file_vault_item import FileVaultItem
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.department_task import DepartmentTask
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
from app.modules.db.models.group_chat_file import GroupChatFile
from app.modules.db.models.group_escalation_settings import GroupEscalationSettings
from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_comment import LeadComment
from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.db.models.lead_opt_order_commission_history import (
    LeadOptOrderCommissionHistory,
)
from app.modules.db.models.lead_opt_order_payment import LeadOptOrderPayment
from app.modules.db.models.message_reply_audit import MessageReplyAudit
from app.modules.db.models.opt_accountant_unit_assignment import OptAccountantUnitAssignment
from app.modules.db.models.opt_buyer import OptBuyer
from app.modules.db.models.opt_requirement import OptRequirement
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.quick_reply_template import QuickReplyTemplate
from app.modules.db.models.quick_reply_template_hidden import QuickReplyTemplateHidden
from app.modules.db.models.refresh_token import RefreshToken
from app.modules.db.models.status import Status
from app.modules.db.models.telephony_account import TelephonyAccount
from app.modules.db.models.telephony_account_group_assignment import (
    TelephonyAccountGroupAssignment,
)
from app.modules.db.models.telephony_call import TelephonyCall
from app.modules.db.models.telephony_extension import TelephonyExtension
from app.modules.db.models.uploaded_file import UploadedFile
from app.modules.db.models.user import User
from app.modules.db.models.user_group_membership import UserGroupMembership

__all__ = [
    "AuditAction",
    "AuditLogEntry",
    "Base",
    "Bot",
    "BotEventInbox",
    "BotGroupAssignment",
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
    "FileShareLink",
    "FileVaultItem",
    "ContactGroupAssignment",
    "DepartmentTask",
    "ContactGroupTransfer",
    "ContactStatus",
    "Department",
    "Group",
    "GroupChatFile",
    "GroupEscalationSettings",
    "Lead",
    "LeadComment",
    "LeadOptOrder",
    "LeadOptOrderLine",
    "LeadOptOrderCommissionHistory",
    "LeadOptOrderPayment",
    "MessageDirection",
    "MessageKind",
    "MessageReplyAudit",
    "OptAccountantUnitAssignment",
    "OptBuyer",
    "OptRequirement",
    "OptUnit",
    "QuickReplyTemplate",
    "QuickReplyTemplateHidden",
    "RefreshToken",
    "Status",
    "StatusKind",
    "TelephonyAccount",
    "TelephonyAccountGroupAssignment",
    "TelephonyCall",
    "TelephonyExtension",
    "TransferStatus",
    "UploadedFile",
    "User",
    "UserAvailability",
    "UserDeletionRequest",
    "UserGroupMembership",
    "UserPresence",
    "UserRole",
    "UserStatus",
]
