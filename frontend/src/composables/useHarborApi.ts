import type { Process } from '@/types/harbor'
import useHarborStore from '@/stores/harbor.store'

/**
 * Fetches and extracts processes from the latest Harbor artifact via the backend API
 * @returns Promise<void>
 * @throws {Error} If there's an error fetching or processing the artifact
 */
export const useHarborApi = () => {
  const harborStore = useHarborStore()

  /**
   * Fetches processes from the latest Harbor artifact via the backend API
   * @returns Promise<void>
   */
  const fetchProcessesFromHarbor = async (): Promise<void> => {
    harborStore.setLoading(true)
    harborStore.setError('')

    try {
      // Call our backend endpoint which will handle the Harbor API call
      const response = await fetch('/api/harbor/processes')

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const errorMsg = `Failed to fetch Harbor processes: ${errorData.detail || response.statusText}`
        harborStore.setError(errorMsg)
        return
      }

      const processes: Process[] = await response.json()
      harborStore.setProcesses(processes)
    } finally {
      harborStore.setLoading(false)
    }
  }

  return { fetchProcessesFromHarbor }
}

export default useHarborApi
