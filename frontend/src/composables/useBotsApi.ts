import { useBotsStore } from '@/stores/bots.store';
import { useHarborApi } from './useHarborApi';
import { useJobsStore } from '@/stores/jobs.store';
import type { Bot } from '@/types';
import useJobsApi from "@/composables/useJobsApi.ts";
import useHarborStore from "@/stores/harbor.store.ts";

export const useBotsApi = () => {
  const botsStore = useBotsStore();
  const harborApi = useHarborApi();
  const harborStore = useHarborStore();
  const jobsApi = useJobsApi();
  const jobsStore = useJobsStore();

  /**
   * Fetches bots by combining data from processes and jobs
   * @returns Promise<void>
   */
  const fetchBots = async (): Promise<void> => {
    botsStore.setLoading(true);
    botsStore.setError('');
    
    try {
      // Fetch processes and jobs in parallel
      await Promise.all([
        harborApi.fetchProcessesFromHarbor(),
        jobsApi.fetchJobs()
      ]);

      const processes = harborStore.processes;
      const jobs = jobsStore.jobs;
      
      // Map processes to bots and update their status based on jobs
      const bots: Bot[] = processes.map(process => {
        // Find a job that matches this process type
        const matchingJob = jobs.find(job => job.name === process.type);

        const isRunning = matchingJob?.status_long.toLowerCase().includes("state 'running'") ?? false;
        const status = isRunning ? 'running' : 'stopped';

        return {
          type: process.type,
          command: process.command,
          args: process.args,
          isRunning,
          status,
          jobName: matchingJob?.name || ''
        };
      });
      
      // Update the store with the latest data
      botsStore.setBots(bots);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
      botsStore.setError(errorMessage);
      console.error('Error in fetchBotsFromArtifact:', errorMessage);
      throw err;
    } finally {
      botsStore.setLoading(false);
    }
  };

  return {
    fetchBots,
  };
};

export default useBotsApi;
