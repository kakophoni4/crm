<script setup lang="ts">
import type { ConnectionSlot } from './device-limit'
defineProps<{ occupiedSlots: number; deviceLimit: number; connections: ConnectionSlot[] }>()
const countries: Record<string, string> = { pl: 'Польша', rs: 'Сербия', ee: 'Эстония', fi: 'Финляндия', ch: 'Швейцария', ro: 'Румыния', kz: 'Казахстан' }
</script>
<template>
  <div class="vpn-connections">
    <strong>Занято {{ occupiedSlots }} из {{ deviceLimit }} подключений</strong>
    <details v-if="connections.length">
      <summary>Подключённые IP</summary>
      <div v-for="slot in connections" :key="slot.ip" class="vpn-connections__slot">
        <code>{{ slot.ip }}</code>
        <span>{{ slot.nodes.split(',').map(id => countries[id] || id).join(', ') }}</span>
        <small>С {{ new Date(slot.connected_at * 1000).toLocaleString('ru-RU') }}</small>
      </div>
    </details>
  </div>
</template>
<style scoped>
.vpn-connections { display: grid; gap: 6px; margin: 12px 0; font-size: 13px; }
.vpn-connections small { color: var(--app-text-muted); font-size: 12px; }
.vpn-connections summary { cursor: pointer; }
.vpn-connections__slot { display: grid; gap: 4px; padding: 8px 0; overflow-wrap: anywhere; }
</style>
