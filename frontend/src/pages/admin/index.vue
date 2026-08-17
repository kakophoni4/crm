<script setup lang="ts">
import {
  NButton,
  NCard,
  NGrid,
  NGridItem,
  NModal,
  NSelect,
  NSpace,
  NSwitch,
  NUpload,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { listUsers, type AdminUser } from '@/features/admin/api'
import { getIdleBannerStatus, patchIdleBanner, sendIdleBanner, uploadIdleBannerImage, fetchIdleBannerImageUrl } from '@/features/idle-banner/api'
import { AppError } from '@/shared/api/http'

const links = [
  { name: 'admin-departments', label: 'Отделы', desc: 'Создание и редактирование отделов' },
  { name: 'admin-groups', label: 'Группы', desc: 'Группы внутри отделов' },
  { name: 'admin-users', label: 'Пользователи', desc: 'Учётные записи, роли, группы' },
  { name: 'admin-bots', label: 'Боты', desc: 'Интеграции, группы и ротация секретов' },
  { name: 'admin-notification-bot', label: 'Бот уведомлений', desc: 'Токен Telegram-бота' },
  { name: 'admin-statuses', label: 'Воронка сделок', desc: 'Этапы открытых сделок (лидов)' },
] as const

const message = useMessage()
const bannerEnabled = ref(false)
const bannerSaving = ref(false)
const bannerUploading = ref(false)
const bannerPreview = ref('/idle-contract-banner.png')
const sendOpen = ref(false)
const sendLoading = ref(false)
const users = ref<AdminUser[]>([])
const selectedUserIds = ref<number[]>([])

const userOptions = computed(() =>
  users.value
    .filter((user) => user.status === 'active')
    .map((user) => ({
      label: `${user.full_name} · ${user.username}`,
      value: user.id,
    })),
)

async function loadBanner(): Promise<void> {
  try {
    const data = await getIdleBannerStatus()
    bannerEnabled.value = data.is_enabled
    const url = await fetchIdleBannerImageUrl(data.has_image)
    if (bannerPreview.value.startsWith('blob:')) URL.revokeObjectURL(bannerPreview.value)
    bannerPreview.value = url
  } catch {
    bannerEnabled.value = false
  }
}

async function onBannerImage(options: { fileList: UploadFileInfo[] }): Promise<void> {
  const file = options.fileList.at(-1)?.file
  if (!(file instanceof File)) return
  bannerUploading.value = true
  try {
    await uploadIdleBannerImage(file)
    await loadBanner()
    message.success('Фото баннера обновлено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить фото')
  } finally {
    bannerUploading.value = false
  }
}

async function onBannerToggle(value: boolean): Promise<void> {
  bannerSaving.value = true
  try {
    const data = await patchIdleBanner(value)
    bannerEnabled.value = data.is_enabled
    message.success(data.is_enabled ? 'Баннер включён' : 'Баннер выключен')
  } catch (err) {
    bannerEnabled.value = !value
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    bannerSaving.value = false
  }
}

async function openSend(): Promise<void> {
  sendOpen.value = true
  if (!users.value.length) {
    try {
      users.value = await listUsers()
    } catch (err) {
      message.error(err instanceof AppError ? err.message : 'Не удалось загрузить пользователей')
    }
  }
}

async function sendNow(): Promise<void> {
  if (!selectedUserIds.value.length) {
    message.warning('Выберите пользователей')
    return
  }
  sendLoading.value = true
  try {
    const data = await sendIdleBanner(selectedUserIds.value)
    message.success(`Показано ${data.sent} пользователям`)
    sendOpen.value = false
    selectedUserIds.value = []
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить')
  } finally {
    sendLoading.value = false
  }
}

onMounted(() => {
  void loadBanner()
})
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <h1 class="admin-page__title">Админка</h1>
      <p class="admin-page__subtitle">Управление организацией и справочниками</p>
      <div class="admin-page__banner">
        <span class="admin-page__banner-label">Баннер</span>
        <NSwitch
          :value="bannerEnabled"
          :loading="bannerSaving"
          size="small"
          @update:value="onBannerToggle"
        />
        <NButton size="tiny" secondary @click="openSend">Показать сейчас</NButton>
        <NUpload
          accept="image/jpeg,image/png,image/webp,image/gif"
          :show-file-list="false"
          :default-upload="false"
          :disabled="bannerUploading"
          @change="onBannerImage"
        >
          <NButton size="tiny" secondary :loading="bannerUploading">Сменить фото</NButton>
        </NUpload>
        <img class="admin-page__banner-preview" :src="bannerPreview" alt="" />
      </div>
    </header>

    <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:3">
      <NGridItem v-for="item in links" :key="item.name">
        <RouterLink :to="{ name: item.name }" class="admin-page__link">
          <NCard :title="item.label" size="small" hoverable>
            {{ item.desc }}
          </NCard>
        </RouterLink>
      </NGridItem>
    </NGrid>

    <NModal
      v-model:show="sendOpen"
      preset="card"
      title="Показать баннер"
      style="width: min(480px, 94vw)"
    >
      <p class="admin-page__hint">Выберите, кому показать баннер прямо сейчас. Закроется по клику или клавише.</p>
      <NSelect
        v-model:value="selectedUserIds"
        multiple
        filterable
        :options="userOptions"
        placeholder="Пользователи"
      />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="sendOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="sendLoading" @click="sendNow">Показать</NButton>
        </NSpace>
      </template>
    </NModal>
  </section>
</template>

<style scoped>
.admin-page__header {
  margin-bottom: 20px;
}

.admin-page__title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.admin-page__subtitle {
  margin: 8px 0 0;
  color: var(--app-text-muted);
}

.admin-page__banner {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding: 8px 12px;
  border: 1px solid var(--n-border-color);
  border-radius: 10px;
}

.admin-page__banner-label {
  font-size: 0.85rem;
  font-weight: 600;
}

.admin-page__banner-preview {
  width: 72px;
  height: 40px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--n-border-color);
}

.admin-page__hint {
  margin: 0 0 12px;
  font-size: 0.85rem;
  color: var(--app-text-muted);
}

.admin-page__link {
  text-decoration: none;
  color: inherit;
  display: block;
}
</style>
