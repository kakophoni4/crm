<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NDropdown } from 'naive-ui'
import { Ellipsis } from 'lucide-vue-next'
const props = defineProps<{
  subscription: { status: string; enabled: boolean; expires_at: number; happ_url: string; clash_url: string; v2rayng_url: string; guide_url: string; ghostlane_url?: string }
  canManage: boolean; canSend?: boolean; showManage?: boolean; busy?: boolean
}>()
const emit = defineEmits<{ copy: [url: string]; renew: []; manage: []; send: []; action: [action: string] }>()
const links = computed(() => [
  { key: props.subscription.ghostlane_url || props.subscription.happ_url?.replace('format=happ', 'format=ghostlane'), label: 'Ghostlane' },
  { key: props.subscription.happ_url, label: 'Happ' }, { key: props.subscription.clash_url, label: 'Koala Clash' },
  { key: props.subscription.v2rayng_url, label: 'v2rayNG' }, { key: props.subscription.guide_url, label: 'Инструкция и APK' },
])
const actions = computed(() => [
  props.subscription.enabled ? { key: 'revoke', label: 'Отключить' } : { key: 'resume', label: 'Включить', disabled: props.subscription.expires_at <= Date.now() / 1000 },
  { key: 'delete', label: 'Удалить', props: { style: { color: 'var(--app-danger)' } } },
])
</script>
<template>
  <div class="vpn-actions">
    <NButton v-if="canSend" size="small" type="primary" secondary :disabled="subscription.status !== 'active' || busy" title="Отправить подписку в чат" @click="emit('send')">Отправить</NButton>
    <NButton v-if="showManage" size="small" secondary @click="emit('manage')">Управление</NButton>
    <NButton v-if="canManage" size="small" :disabled="busy" @click="emit('renew')">Продлить</NButton>
    <NDropdown trigger="click" :options="links" @select="url => emit('copy', String(url))"><NButton size="small" :disabled="subscription.status !== 'active'" title="Скопировать ссылку для приложения">Ссылки</NButton></NDropdown>
    <NDropdown v-if="canManage" trigger="click" :options="actions" @select="action => emit('action', String(action))"><NButton size="small" quaternary :disabled="busy" aria-label="Действия с подпиской"><template #icon><Ellipsis :size="18" /></template></NButton></NDropdown>
  </div>
</template>
<style scoped>
.vpn-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
</style>
