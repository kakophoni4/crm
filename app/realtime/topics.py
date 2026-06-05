from __future__ import annotations

"""WS / event-bus topic slugs (must match publishers in modules)."""

CHAT_MESSAGE_INBOUND = "chat.message.inbound"
CHAT_MESSAGE_ATTACHMENT_READY = "chat.message.attachment_ready"
CHAT_MESSAGE_OUTBOUND = "chat.message.outbound.requested"
CHAT_TRANSFER_REQUESTED = "chat.transfer.requested"
CHAT_TRANSFER_APPROVED = "chat.transfer.approved"
CHAT_TRANSFER_ACCEPTED = "chat.transfer.accepted"
CHAT_TRANSFER_DECLINED = "chat.transfer.declined"
CHAT_TRANSFER_FORCED = "chat.transfer.forced"
CHAT_TAKEOVER_STARTED = "chat.takeover.started"
CHAT_TAKEOVER_RELEASED = "chat.takeover.released"
CHAT_STATUS_CHANGED = "chat.status_changed"
CONTACT_UPDATED = "contact.updated"
CONTACT_OWNERSHIP_ASSIGNED = "contact.ownership.assigned"
CONTACT_OWNERSHIP_REASSIGNED = "contact.ownership.reassigned"
CONTACT_ESCALATION_OWNER_NOTIFY = "contact.escalation.owner_notify"
CONTACT_ESCALATION_GROUP_NOTIFY = "contact.escalation.group_notify"
MESSAGE_REPLIED_ON_BEHALF = "message.replied.on_behalf"
BOT_HEALTH_CHANGED = "bot.health_changed"
BOT_SIGNATURE_INVALID = "bot.signature_invalid"
PRESENCE_USER_CHANGED = "presence.user.changed"

ADMIN_ONLY_TOPICS: frozenset[str] = frozenset(
    {
        BOT_HEALTH_CHANGED,
        BOT_SIGNATURE_INVALID,
    },
)
