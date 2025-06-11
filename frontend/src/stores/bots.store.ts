import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { Bot } from '@/types'
import { useHarborStore } from '@/stores/harbor.store'
import { useJobsStore } from '@/stores/jobs.store'

export const useBotsStore = defineStore('bots', () => {
  // Child stores
  const harborStore = useHarborStore()
  const jobsStore = useJobsStore()

  // State
  const loading = ref(false)
  const error = ref('')
  const bots = ref<Bot[]>([])
  const lastRefreshed = ref<Date | null>(null)
  const hasPendingJobs = ref(false)

  // Actions
  const setError = (errorMessage: string) => {
    error.value = errorMessage
  }

  const setBots = (newBots: Bot[]) => {
    bots.value = newBots
  }

  const setLastRefreshed = () => {
    lastRefreshed.value = new Date()
  }

  const setLoading = (isLoading: boolean) => {
    loading.value = isLoading
  }

  const updateHasPendingJobs = () => {
    hasPendingJobs.value = bots.value.some((bot) => bot.status.isPending)
  }

  // Watchers
  watch(bots, updateHasPendingJobs, { immediate: true })

  return {
    // State
    hasPendingJobs,
    error,
    loading: computed(() => loading.value || harborStore.loading || jobsStore.loading),

    // Getters
    bots,
    lastRefreshed,

    // Actions
    setError,
    setBots,
    setLastRefreshed,
    setLoading,
  }
})

export default useBotsStore
