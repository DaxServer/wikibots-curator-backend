import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Job } from '@/types'

export const useJobsStore = defineStore('jobs', () => {
  // State
  const loading = ref(false)
  const error = ref('')
  const jobs = ref<Job[]>([])
  const starting = ref<Record<string, boolean>>({})
  const deleting = ref<Record<string, boolean>>({})

  // Actions
  const setLoading = (isLoading: boolean) => {
    loading.value = isLoading
  }

  const setError = (errorMessage: string) => {
    error.value = errorMessage
  }

  const setJobs = (newJobs: Job[]) => {
    jobs.value = newJobs
  }

  const setStarting = (jobName: string, isStarting: boolean) => {
    if (isStarting) {
      starting.value[jobName] = true
    } else {
      delete starting.value[jobName]
    }
  }

  const setDeleting = (jobName: string, isDeleting: boolean) => {
    if (isDeleting) {
      deleting.value[jobName] = true
    } else {
      delete deleting.value[jobName]
    }
  }

  return {
    // State
    loading,
    error,
    jobs,
    starting,
    deleting,

    // Actions
    setLoading,
    setError,
    setJobs,
    setStarting,
    setDeleting,
  }
})

export default useJobsStore
