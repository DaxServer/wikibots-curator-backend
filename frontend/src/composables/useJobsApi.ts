import { useJobsStore } from '@/stores/jobs.store'
import type { JobRequest } from '@/types'

export const useJobsApi = () => {
  const jobsStore = useJobsStore()

  /**
   * Handles API response errors and sets the error state.
   * @param response - The API response object.
   * @param action - A string describing the action being performed (e.g., 'fetch jobs').
   */
  const handleApiResponseError = async (response: Response, action: string): Promise<void> => {
    const errorData = await response.json().catch(() => ({}))
    const errorMsg = `Failed to ${action}: ${errorData.message || response.statusText}`
    jobsStore.setError(errorMsg)
  }

  /**
   * Fetches the list of jobs
   * @returns Promise<void>
   */
  const fetchJobs = async (): Promise<void> => {
    jobsStore.setLoading(true)
    jobsStore.setError('')

    try {
      const response = await fetch('/api/toolforge/jobs/v1/tool/curator/jobs/', {
        signal: AbortSignal.timeout(60000),
      })

      if (!response.ok) {
        await handleApiResponseError(response, 'fetch jobs')
        return
      }

      const data = await response.json()
      jobsStore.setJobs(data.jobs || [])
    } finally {
      jobsStore.setLoading(false)
    }
  }

  /**
   * Deletes a job by name
   * @param jobName - The name of the job to delete
   * @returns Promise<boolean> - Returns true if successful
   */
  const deleteJob = async (jobName: string): Promise<void> => {
    jobsStore.setDeleting(jobName, true)
    jobsStore.setError('')

    try {
      const response = await fetch(
        `/api/toolforge/jobs/v1/tool/curator/jobs/${encodeURIComponent(jobName)}`,
        {
          method: 'DELETE',
          signal: AbortSignal.timeout(60000),
        }
      )

      if (!response.ok) {
        await handleApiResponseError(response, 'delete job')
        return
      }
    } finally {
      jobsStore.setDeleting(jobName, false)
    }
  }

  /**
   * Starts a new job
   * @returns Promise<boolean> - Returns true if successful
   * @param jobName
   */
  const startJob = async (jobName: string): Promise<void> => {
    jobsStore.setStarting(jobName, true)
    jobsStore.setError('')

    const job: JobRequest = {
      name: jobName,
      cmd: jobName,
      imagename: 'tool-curator/wikibots:latest',
      continuous: true,
    }

    try {
      const response = await fetch('/api/toolforge/jobs/v1/tool/curator/jobs/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(job),
        signal: AbortSignal.timeout(60000),
      })

      if (!response.ok) {
        await handleApiResponseError(response, 'start job')
      }
    } finally {
      jobsStore.setStarting(job.name, false)
    }
  }

  return {
    // Methods
    fetchJobs,
    deleteJob,
    startJob,
  }
}

export default useJobsApi
