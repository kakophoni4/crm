<script setup lang="ts">
import { useIdle } from '@vueuse/core'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { getIdleBannerStatus } from '@/features/idle-banner/api'
import { connectIdleBannerRealtime } from '@/shared/realtime/idle-banner-ws'

const IDLE_MS = 10 * 60 * 1000

const { idle } = useIdle(IDLE_MS, {
  events: [
    'mousemove',
    'mousedown',
    'mouseup',
    'keydown',
    'keyup',
    'scroll',
    'touchstart',
    'touchmove',
    'wheel',
    'pointerdown',
    'pointermove',
  ],
})
const enabled = ref(false)
const forceShow = ref(false)
const pageFocused = ref(
  typeof document === 'undefined' ? true : document.hasFocus() && !document.hidden,
)

const visible = computed(
  () => forceShow.value || (enabled.value && idle.value && pageFocused.value),
)

function markUnfocused(): void {
  pageFocused.value = false
}

function markFocused(): void {
  pageFocused.value = !document.hidden && document.hasFocus()
}

function onVisibility(): void {
  if (document.hidden) markUnfocused()
  else markFocused()
}

function dismissForced(): void {
  forceShow.value = false
}

function onKeyDown(event: KeyboardEvent): void {
  if (event.key === 'PrintScreen') {
    pageFocused.value = false
    forceShow.value = false
    window.setTimeout(() => {
      pageFocused.value = !document.hidden && document.hasFocus()
    }, 1500)
    return
  }
  dismissForced()
}

onMounted(() => {
  window.addEventListener('blur', markUnfocused)
  window.addEventListener('focus', markFocused)
  window.addEventListener('beforeprint', markUnfocused)
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('keydown', onKeyDown, true)
  window.addEventListener('pointerdown', dismissForced, true)
  window.addEventListener('touchstart', dismissForced, true)
  void getIdleBannerStatus()
    .then((data) => {
      enabled.value = data.is_enabled
    })
    .catch(() => {
      enabled.value = false
    })
  void connectIdleBannerRealtime(
    (isEnabled) => {
      enabled.value = isEnabled
      if (!isEnabled) forceShow.value = false
    },
    () => {
      forceShow.value = true
    },
  )
})

onUnmounted(() => {
  window.removeEventListener('blur', markUnfocused)
  window.removeEventListener('focus', markFocused)
  window.removeEventListener('beforeprint', markUnfocused)
  document.removeEventListener('visibilitychange', onVisibility)
  window.removeEventListener('keydown', onKeyDown, true)
  window.removeEventListener('pointerdown', dismissForced, true)
  window.removeEventListener('touchstart', dismissForced, true)
})
</script>

<template>
  <Teleport to="body">
    <div
      v-show="visible"
      class="idle-banner"
      role="presentation"
      aria-hidden="true"
      @contextmenu.prevent
      @dragstart.prevent
    >
      <img
        class="idle-banner__img"
        src="/idle-contract-banner.png"
        alt=""
        draggable="false"
      />
    </div>
  </Teleport>
</template>

<style scoped>
.idle-banner {
  position: fixed;
  inset: 0;
  z-index: 20000;
  background: #111;
  user-select: none;
  -webkit-user-select: none;
  -webkit-user-drag: none;
}

.idle-banner__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
}
</style>
