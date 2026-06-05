<script setup lang="ts">
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSpace,
  useMessage,
  type FormInst,
  type FormRules,
} from 'naive-ui'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const router = useRouter()
const route = useRoute()
const message = useMessage()
const auth = useAuthStore()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)

const model = ref({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [
    { required: true, message: 'Введите логин', trigger: ['blur', 'input'] },
    {
      validator: (_rule, value: string) => {
        const login = value?.trim() ?? ''
        if (!login) return true
        if (/^[a-zA-Z0-9_]+$/.test(login)) return true
        if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(login)) return true
        return new Error('Введите логин (латиница, цифры, _) или email')
      },
      trigger: ['blur', 'input'],
    },
  ],
  password: [
    { required: true, message: 'Введите пароль', trigger: ['blur', 'input'] },
    { min: 1, message: 'Пароль не может быть пустым', trigger: ['blur', 'input'] },
  ],
}

async function onSubmit(): Promise<void> {
  await formRef.value?.validate()
  loading.value = true
  try {
    await auth.login(model.value.username.trim(), model.value.password)
    const redirect =
      typeof route.query.redirect === 'string' ? route.query.redirect : '/chats'
    await router.replace(redirect)
  } catch (err) {
    const text =
      err instanceof AppError ? err.message : 'Не удалось войти. Проверьте логин и пароль.'
    message.error(text)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <NCard title="Вход в CRM" class="login-page__card">
      <NForm ref="formRef" :model="model" :rules="rules" @submit.prevent="onSubmit">
        <NFormItem label="Логин" path="username">
          <NInput
            v-model:value="model.username"
            type="text"
            autocomplete="username"
            placeholder="Логин или email"
            :disabled="loading"
            @keyup.enter="onSubmit"
          />
        </NFormItem>
        <NFormItem label="Пароль" path="password">
          <NInput
            v-model:value="model.password"
            type="password"
            show-password-on="click"
            autocomplete="current-password"
            :disabled="loading"
            @keyup.enter="onSubmit"
          />
        </NFormItem>
        <NSpace justify="end">
          <NButton type="primary" attr-type="submit" :loading="loading" @click="onSubmit">
            Войти
          </NButton>
        </NSpace>
      </NForm>
    </NCard>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--app-bg);
}

.login-page__card {
  width: 100%;
  max-width: 400px;
}
</style>
