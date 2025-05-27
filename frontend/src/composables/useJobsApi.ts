import { useJobsStore } from '@/stores/jobs.store';
import type { 
  JobRequest
} from '@/types';

export const useJobsApi = () => {
  const jobsStore = useJobsStore();

  /**
   * Fetches the list of jobs
   * @returns Promise<void>
   */
  const fetchJobs = async (): Promise<void> => {
    jobsStore.setLoading(true);
    jobsStore.setError('');
    
    try {
      const response = await fetch('/curator-api/api/toolforge/jobs/v1/tool/curator/jobs/');
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.message || `Failed to fetch jobs: ${response.statusText}`;
        throw new Error(errorMsg);
      }
      
      const data = await response.json();
      const jobs = data.jobs || [];

      jobsStore.setJobs(jobs);
    } finally {
      jobsStore.setLoading(false);
    }
  };

  /**
   * Deletes a job by name
   * @param jobName - The name of the job to delete
   * @returns Promise<boolean> - Returns true if successful
   */
  const deleteJob = async (jobName: string): Promise<void> => {
    jobsStore.setDeleting(jobName, true);
    
    try {
      const response = await fetch(
        `/curator-api/api/toolforge/jobs/v1/tool/curator/jobs/${encodeURIComponent(jobName)}`,
        { method: 'DELETE' }
      );
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.message || `Failed to delete job: ${response.statusText}`;
        throw new Error(errorMsg);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
      jobsStore.setError('Failed to delete job. Please try again.');
      console.error('Error in deleteJob:', errorMessage);
      throw err;
    } finally {
      jobsStore.setDeleting(jobName, false);
    }
  };

  /**
   * Starts a new job
   * @returns Promise<boolean> - Returns true if successful
   * @param jobName
   */
  const startJob = async (jobName: string): Promise<void> => {
    jobsStore.setStarting(jobName, true);

    const job: JobRequest = {
      name: jobName,
      cmd: jobName,
      imagename: 'tool-curator/wikibots:latest',
      continuous: true,
    };
    
    try {
      const response = await fetch('/curator-api/api/toolforge/jobs/v1/tool/curator/jobs/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(job),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.message || `Failed to start job: ${response.statusText}`;
        throw new Error(errorMsg);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
      jobsStore.setError('Failed to start job. Please try again.');
      console.error('Error in startJob:', errorMessage);
      throw err;
    } finally {
      jobsStore.setStarting(job.name, false);
    }
  };

  return {
    // Methods
    fetchJobs,
    deleteJob,
    startJob,
  };
};

export default useJobsApi;
