import { ref, onUnmounted } from 'vue';
import { useBotsStore } from '@/stores/bots.store';
import { useHarborApi } from './useHarborApi';
import useJobsApi from "@/composables/useJobsApi.ts";
import useHarborStore from "@/stores/harbor.store.ts";
import useJobsStore from "@/stores/jobs.store.ts";
import useBotStatus from "@/composables/useBotStatus.ts";

export const useBotsApi = () => {
  const botsStore = useBotsStore();
  const harborApi = useHarborApi();
  const jobsApi = useJobsApi();
  const harborStore = useHarborStore();
  const jobsStore = useJobsStore();
  const { updateBotsWithJobStatus, statusConfig } = useBotStatus();

  /**
   * Maps processes and jobs to Bot objects with status information
   * and updates the bots store
   */
  const mapProcessesToBots = (): void => {
    const processes = harborStore.processes;
    const jobs = jobsStore.jobs;

    // First, create basic bot objects from processes
    const basicBots = processes.map(process => ({
      type: process.type,
      command: process.command,
      args: process.args,
      status: {
        state: 'stopped' as const,
        ...statusConfig.stopped,
        isPending: false
      },
      jobName: ''
    }));

    // Then update them with job status information
    const botsWithStatus = updateBotsWithJobStatus(basicBots, jobs);

    botsStore.setBots(botsWithStatus);
  };

  /**
   * Fetches bots by combining data from processes and jobs
   * @returns Promise<void>
   */
  const fetchBots = async (): Promise<void> => {
    botsStore.setError('');
    
    try {
      // Fetch processes and jobs in parallel
      await Promise.all([
        harborApi.fetchProcessesFromHarbor(),
        jobsApi.fetchJobs()
      ]);

      // This will update the bots in the store directly
      mapProcessesToBots();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
      botsStore.setError(errorMessage);
      console.error('Error in fetchBotsFromArtifact:', errorMessage);
      throw err;
    }
  };

  const fetchJobs = async (): Promise<void> => {
    await jobsApi.fetchJobs();
    mapProcessesToBots();
  };

  // Poll jobs when there are pending jobs
  const pollInterval = ref<number | null>(null);
  const POLL_INTERVAL_MS = 2000; // 2 seconds

  const startPolling = (): void => {
    // Clear any existing interval
    stopPolling();
    
    pollInterval.value = window.setInterval(async () => {
      try {
        await fetchJobs();
        
        // Check if there are no more pending jobs
        if (!botsStore.hasPendingJobs) {
          stopPolling();
        }
      } catch (error) {
        console.error('Error while polling jobs:', error);
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  };

  const stopPolling = (): void => {
    if (pollInterval.value !== null) {
      clearInterval(pollInterval.value);
      pollInterval.value = null;
    }
  };

  // Clean up interval when component is unmounted
  onUnmounted(stopPolling);

  return {
    fetchBots,
    fetchJobs,
    startPolling,
    stopPolling,
  };
};

export default useBotsApi;
