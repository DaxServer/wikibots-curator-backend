import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<string>('')
  const isAuthenticated = computed(() => !!user.value)
  const isAuthorized = ref(false)
  const isLoading = ref(false)

  const reset = () => {
    user.value = ''
    isAuthorized.value = false
  }

  const login = () => {
    window.location.href = '/auth/login'
  }

  const logout = async () => {
    try {
      // Call backend logout endpoint
      await fetch('/auth/logout')
      reset()
    } catch (error) {
      console.error('Logout failed:', error)
    }
  }

  const checkAuth = async () => {
    isLoading.value = true
    try {
      const response = await fetch('/auth/whoami')
      if (response.ok) {
        const userData = await response.json()
        user.value = userData['username']
        isAuthorized.value = userData['authorized']
      } else {
        reset()
      }
    } catch (error) {
      console.error('Authentication check failed:', error)
      reset()
    } finally {
      isLoading.value = false
    }
  }

  return {
    user,
    isAuthenticated,
    isAuthorized,
    login,
    logout,
    checkAuth,
    isLoading,
  }
})
