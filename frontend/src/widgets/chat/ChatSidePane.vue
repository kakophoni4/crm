<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { NTab, NTabs, type SelectOption } from 'naive-ui'
import type { ChatDetail } from '@/entities/chat/types'
import type { BotListItem } from '@/entities/bot/types'
import { useAuthStore } from '@/shared/store/auth'
import { useChatNotificationsStore } from '@/features/chats/notifications-store'
import ChatsNotificationsPane from './ChatsNotificationsPane.vue'
const ChatDealSidePanel = defineAsyncComponent(() => import('./ChatDealSidePanel.vue'))
const ChatPaymentsSidePanel = defineAsyncComponent(() => import('./ChatPaymentsSidePanel.vue'))
const ContactVpnPanel = defineAsyncComponent(() => import('./ContactVpnPanel.vue'))
const ChatClientRequirementPanel = defineAsyncComponent(
  () => import('./ChatClientRequirementPanel.vue'),
)
defineProps<{
  chat: ChatDetail | null
  bots: BotListItem[]
  leadStatusOptions: SelectOption[]
  wonStatusId: number | null
  lostStatusId: number | null
}>()
const activeTab = defineModel<'deal' | 'payments' | 'vpn' | 'client_req' | 'notifications'>({
  required: true,
})
const auth = useAuthStore()
const notifications = useChatNotificationsStore()
</script>
<template>
  <section class="chat-side-pane">
    <NTabs
      v-if="chat"
      v-model:value="activeTab"
      type="line"
      size="medium"
      class="chat-side-pane__tabs"
    >
      <NTab name="deal" tab="Сделки" />
      <NTab name="payments" tab="Оплаты" />
      <NTab v-if="auth.user?.permissions?.includes('contacts.read')" name="vpn" tab="VPN" />
      <NTab name="client_req" tab="От клиента" />
      <NTab name="notifications">
        <template #default>
          <span class="chat-side-pane__tab-label">
            Уведомления
            <span v-if="notifications.unreadCount" class="chat-side-pane__tab-badge">
              {{ notifications.unreadCount > 99 ? '99+' : notifications.unreadCount }}
            </span>
          </span>
        </template>
      </NTab>
    </NTabs>
    <ContactVpnPanel
      v-if="chat && activeTab === 'vpn' && auth.user?.permissions?.includes('contacts.read')"
      :key="`vpn-${chat?.id}`"
      :contact-id="chat.contact_id"
      :bot-id="chat.bot_id"
      :chat-id="chat.id"
    />
    <ChatDealSidePanel
      v-else-if="chat && activeTab === 'deal'"
      :key="`deal-${chat?.id}`"
      :chat="chat"
      :bots="bots"
      :lead-status-options="leadStatusOptions"
      :won-status-id="wonStatusId"
      :lost-status-id="lostStatusId"
    />
    <ChatPaymentsSidePanel
      v-else-if="chat && activeTab === 'payments'"
      :key="`pay-${chat?.id}`"
      :chat="chat"
    />
    <ChatClientRequirementPanel
      v-else-if="chat && activeTab === 'client_req'"
      :key="`creq-${chat?.id}`"
      :chat="chat"
    />
    <ChatsNotificationsPane v-else embedded :hide-title="!!chat" />
  </section>
</template>
<style scoped>
.chat-side-pane {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.chat-side-pane__tabs {
  flex-shrink: 0;
  padding: 10px 10px 0;
  border-bottom: 1px solid var(--app-border);
  min-width: 0;
}

.chat-side-pane__tabs :deep(.n-tabs-nav) {
  width: 100%;
}

.chat-side-pane__tabs :deep(.n-tabs-tab) {
  padding: 10px 4px 12px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.chat-side-pane__tabs :deep(.n-tabs-tab-pad) {
  width: 12px;
}
.chat-side-pane__tab-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  gap: 5px;
  max-width: 100%;
  text-align: center;
}

.chat-side-pane__tab-badge {
  flex-shrink: 0;
  min-width: 1.25rem;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--app-accent, #2080f0);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1.35rem;
  text-align: center;
}

.chat-side-pane > :not(.chat-side-pane__tabs) {
  flex: 1;
  min-height: 0;
  min-width: 0;
}
</style>
