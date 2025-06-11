import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import 'primeicons/primeicons.css' // Icons
import '@/assets/main.css' // Tailwind CSS

import App from './App.vue'

// Create app
const app = createApp(App)

// Create Pinia
const pinia = createPinia()

// Register plugins
app.use(pinia)
app.use(PrimeVue, {
  theme: {
    preset: Aura,
  },
})

// Mount the app
app.mount('#app')
