import { onMounted, onUnmounted, type Ref } from 'vue'
import { useRoute } from 'vue-router'

import { focusChatListSearch } from '@/features/chats/chat-list-search-focus'
import { usePhoneChatsOnly } from '@/shared/lib/phone-mode'

function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  return target.isContentEditable
}

export function useAppHotkeys(globalSearchOpen: Ref<boolean>): void {
  const route = useRoute()
  const phoneChatsOnly = usePhoneChatsOnly()

  function onKeydown(event: KeyboardEvent): void {
    const key = event.key.toLowerCase()
    if (phoneChatsOnly.value) return

    if ((event.ctrlKey || event.metaKey) && key === 'k') {
      event.preventDefault()
      globalSearchOpen.value = true
      return
    }

    if (key === 'escape' && globalSearchOpen.value) {
      globalSearchOpen.value = false
      return
    }

    if (
      key === '/' &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      !globalSearchOpen.value &&
      route.name === 'chats' &&
      !isEditableTarget(event.target)
    ) {
      event.preventDefault()
      focusChatListSearch()
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeydown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', onKeydown)
  })
}
