<script setup lang="ts">
import { useIdle } from '@vueuse/core'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { fetchIdleBannerImageUrl, getIdleBannerStatus } from '@/features/idle-banner/api'
import { connectIdleBannerRealtime } from '@/shared/realtime/idle-banner-ws'

const IDLE_MS = 10 * 60 * 1000
const DEFAULT_BANNER = '/idle-contract-banner.png'

const { idle, reset } = useIdle(IDLE_MS, {
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
const imageUrl = ref(DEFAULT_BANNER)
const imageVersion = ref(0)
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

function dismissBanner(): void {
  if (!visible.value) return
  forceShow.value = false
  reset()
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
  dismissBanner()
}

function setImageUrl(url: string): void {
  if (imageUrl.value.startsWith('blob:')) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = url
}

async function loadImage(hasImage: boolean, version: number): Promise<void> {
  imageVersion.value = version
  const url = await fetchIdleBannerImageUrl(hasImage)
  setImageUrl(url)
}

onMounted(() => {
  window.addEventListener('blur', markUnfocused)
  window.addEventListener('focus', markFocused)
  window.addEventListener('beforeprint', markUnfocused)
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('keydown', onKeyDown, true)
  window.addEventListener('pointerdown', dismissBanner, true)
  window.addEventListener('pointermove', dismissBanner, true)
  window.addEventListener('mousemove', dismissBanner, true)
  window.addEventListener('wheel', dismissBanner, true)
  window.addEventListener('touchstart', dismissBanner, true)
  window.addEventListener('touchmove', dismissBanner, true)
  void getIdleBannerStatus()
    .then(async (data) => {
      enabled.value = data.is_enabled
      await loadImage(data.has_image, data.image_version)
    })
    .catch(() => {
      enabled.value = false
    })
  void connectIdleBannerRealtime(
    (payload) => {
      enabled.value = payload.is_enabled
      if (!payload.is_enabled) forceShow.value = false
      const version = payload.image_version ?? 0
      if (version !== imageVersion.value) {
        void loadImage(Boolean(payload.has_image), version)
      }
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
  window.removeEventListener('pointerdown', dismissBanner, true)
  window.removeEventListener('pointermove', dismissBanner, true)
  window.removeEventListener('mousemove', dismissBanner, true)
  window.removeEventListener('wheel', dismissBanner, true)
  window.removeEventListener('touchstart', dismissBanner, true)
  window.removeEventListener('touchmove', dismissBanner, true)
  setImageUrl(DEFAULT_BANNER)
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
        :src="imageUrl"
        alt=""
        draggable="false"
      />
    </div>
  </Teleport>
</template>

<style scoped>
.idle-banner {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 20000;
  width: min(280px, 32vw);
  pointer-events: none;
  overflow: hidden;
  border-radius: 10px;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.12),
    0 12px 32px rgba(0, 0, 0, 0.28);
  user-select: none;
  -webkit-user-select: none;
  -webkit-user-drag: none;
  animation: idle-banner-in 0.35s ease-out;
}

.idle-banner__img {
  display: block;
  width: 100%;
  height: auto;
  max-height: 200px;
  object-fit: cover;
  pointer-events: none;
}

@keyframes idle-banner-in {
  from {
    opacity: 0;
    transform: translate(12px, 12px);
  }
  to {
    opacity: 1;
    transform: translate(0, 0);
  }
}
</style>
