<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInputNumber } from 'naive-ui'
import { periodEnd, subscriptionPeriods, trialPeriods, validPeriod } from './period'

const props = withDefaults(defineProps<{ modelValue: number | null; trial?: boolean; expiresAt?: number; disabled?: boolean }>(), { expiresAt: 0 })
const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()
const periods = computed(() => props.trial ? trialPeriods : subscriptionPeriods)
const end = computed(() => validPeriod(props.modelValue) ? new Date(periodEnd(props.modelValue, props.expiresAt) * 1000).toLocaleString('ru-RU') : '')
</script>

<template>
  <div class="period-picker">
    <span class="period-label">{{ expiresAt ? 'Добавить к подписке' : trial ? 'Пробный период' : 'Срок подписки' }}</span>
    <div class="presets" role="group" aria-label="Выбрать количество дней">
      <NButton v-for="period in periods" :key="period" size="small" :type="modelValue === period ? 'primary' : 'default'" :secondary="modelValue === period" :disabled="disabled" :aria-pressed="modelValue === period" @click="emit('update:modelValue', period)">{{ period }} дн.</NButton>
    </div>
    <label class="custom">Другой срок, дней<NInputNumber :value="modelValue" :min="1" :max="3650" :precision="0" :disabled="disabled" placeholder="Количество дней" @update:value="value => emit('update:modelValue', value)" /></label>
    <p v-if="end" class="hint">{{ expiresAt ? 'Новый срок до' : 'Действует до' }} {{ end }}<span v-if="expiresAt && expiresAt <= Date.now() / 1000"> · отсчёт с сегодняшнего дня</span></p>
  </div>
</template>

<style scoped>
.period-picker{display:grid;gap:10px;min-width:0}.period-label{font-weight:600}.presets{display:flex;flex-wrap:wrap;gap:8px}.custom{display:grid;grid-template-columns:1fr 145px;align-items:center;gap:12px;font-size:13px}.hint{margin:0;color:var(--text-secondary,#8a93a3);font-size:12px}
</style>
