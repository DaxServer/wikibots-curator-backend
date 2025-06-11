import { onUnmounted, watch } from 'vue'
import { useBotsStore } from '@/stores/bots.store'
import { useHarborApi } from './useHarborApi'
import useJobsApi from '@/composables/useJobsApi'
import useHarborStore from '@/stores/harbor.store'
import useJobsStore from '@/stores/jobs.store'
import useBotStatus from '@/composables/useBotStatus'

export const useBotsApi = () => {
  const botsStore = useBotsStore()
  const harborApi = useHarborApi()
  const jobsApi = useJobsApi()
  const harborStore = useHarborStore()
  const jobsStore = useJobsStore()
  const { updateBotsWithJobStatus, statusConfig } = useBotStatus()

  /**
   * Maps processes and jobs to Bot objects with status information
   * and updates the bots store
   */
  const mapProcessesToBots = (): void => {
    const processes = harborStore.processes
    const jobs = jobsStore.jobs

    // First, create basic bot objects from processes
    const basicBots = processes.map((process) => ({
      type: process.type,
      command: process.command,
      args: process.args,
      status: {
        state: 'stopped' as const,
        ...statusConfig.stopped,
        isPending: false,
      },
      jobName: '',
    }))

    // Then update them with job status information
    const botsWithStatus = updateBotsWithJobStatus(basicBots, jobs)

    botsStore.setBots(botsWithStatus)
  }

  /**
   * Fetches bots by combining data from processes and jobs
   * @returns Promise<void>
   */
  const fetchBots = async (): Promise<void> => {
    await Promise.all([harborApi.fetchProcessesFromHarbor(), jobsApi.fetchJobs()])

    // This will update the bots in the store directly
    mapProcessesToBots()
  }

  const fetchJobs = async (): Promise<void> => {
    await jobsApi.fetchJobs()
    mapProcessesToBots()
  }

  // Polling
  let pollInterval: number | null = null
  const POLL_INTERVAL_MS = 2000 // 2 seconds

  const startPolling = () => {
    if (pollInterval !== null) {
      clearInterval(pollInterval)
    }

    pollInterval = window.setInterval(async () => {
      try {
        await fetchJobs()
      } catch (e) {
        jobsStore.setError(`Error fetching jobs: ${e}`)
        stopPolling()
      }
    }, POLL_INTERVAL_MS)
  }

  const stopPolling = () => {
    if (pollInterval !== null) {
      clearInterval(pollInterval)
      pollInterval = null
    }
  }

  watch(
    () => botsStore.hasPendingJobs,
    (newVal) => {
      if (newVal) {
        startPolling()
      } else {
        stopPolling()
      }
    }
  )

  onUnmounted(() => {
    stopPolling()
  })

  return {
    fetchBots,
    fetchJobs,
    startPolling, // Expose startPolling if needed elsewhere, though watch handles it
    stopPolling, // Expose stopPolling if needed elsewhere
  }
}

export default useBotsApi
