<script setup lang="ts">
import Button from 'primevue/button'
import Toolbar from 'primevue/toolbar'
import { useAuthStore } from '@/stores/auth.store'
import { onMounted } from 'vue'

const authStore = useAuthStore()

const handleLogin = () => authStore.login()
const handleLogout = () => authStore.logout()

onMounted(() => {
  authStore.checkAuth()
})
</script>

<template>
  <Toolbar class="flex justify-between items-center">
    <template #start>
      <h1>CuratorBot - Toolforge Jobs</h1>
    </template>
    <template #end>
      <div
        v-if="authStore.isAuthenticated"
        class="flex items-center space-x-2"
      >
        <span>Welcome, {{ authStore.user }}!</span>
        <Button
          label="Logout"
          severity="secondary"
          size="small"
          @click="handleLogout"
        />
      </div>
      <div v-else>
        <Button
          label="Login with Wikimedia Commons"
          severity="secondary"
          size="small"
          @click="handleLogin"
          :loading="authStore.isLoading"
          :disabled="authStore.isLoading"
        />
      </div>
    </template>
  </Toolbar>
</template>
