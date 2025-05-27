import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Bot, Job } from '@/types';
import useBotStatus from '@/composables/useBotStatus';

export const useBotsStore = defineStore('bots', () => {
  // State
  const loading = ref(false);
  const error = ref('');
  const bots = ref<Bot[]>([]);

  // Composable
  const { updateBotsWithJobStatus: updateBotsWithJobStatusUtil, botsWithStatus: botsWithStatusUtil } = useBotStatus();
  
  // Actions
  const setLoading = (isLoading: boolean) => {
    loading.value = isLoading;
  };

  const setError = (errorMessage: string) => {
    error.value = errorMessage;
  };

  const setBots = (newBots: Bot[]) => {
    bots.value = newBots.map(bot => ({
      ...bot,
      isRunning: bot.status === 'running'
    }));
  };

  const updateBotsWithJobStatus = (jobs: Job[]) => {
    bots.value = updateBotsWithJobStatusUtil(bots.value, jobs);
  };

  return {
    // State
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    
    // Getters
    bots: computed(() => botsWithStatusUtil(bots.value)),

    // Actions
    setLoading,
    setError,
    setBots,
    updateBotsWithJobStatus,
  };
});

export default useBotsStore;
