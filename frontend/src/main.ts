import { createApp } from 'vue'



import App from '@/app/App.vue'

import { setupProviders } from '@/app/providers'

import { router } from '@/app/router'

import { initSentry } from '@/app/sentry'

import '@/style.css'



const app = createApp(App)

initSentry(app, router)

setupProviders(app)

app.mount('#app')

