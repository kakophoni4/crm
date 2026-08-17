<script setup lang="ts">
import { useIdle } from '@vueuse/core'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { fetchIdleBannerImageUrl, getIdleBannerStatus } from '@/features/idle-banner/api'
import { connectIdleBannerRealtime } from '@/shared/realtime/idle-banner-ws'

const IDLE_MS = 10 * 60 * 1000
const DEFAULT_BANNER = '/idle-contract-banner.png'

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
  window.addEventListener('pointerdown', dismissForced, true)
  window.addEventListener('touchstart', dismissForced, true)
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
  window.removeEventListener('pointerdown', dismissForced, true)
  window.removeEventListener('touchstart', dismissForced, true)
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
