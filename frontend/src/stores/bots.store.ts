import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Bot } from '@/types';
import { useHarborStore } from './harbor.store';
import { useJobsStore } from './jobs.store';

export const useBotsStore = defineStore('bots', () => {
  // Child stores
  const harborStore = useHarborStore();
  const jobsStore = useJobsStore();
  
  // State
  const error = ref('');
  const bots = ref<Bot[]>([]);
  const lastRefreshed = ref<Date | null>(null);

  // Actions
  const setError = (errorMessage: string) => {
    error.value = errorMessage;
  };

  const setBots = (newBots: Bot[]) => {
    bots.value = newBots;
  };

  const setLastRefreshed = () => {
    lastRefreshed.value = new Date();
  };

  return {
    // State
    error: computed(() => error.value || harborStore.error || jobsStore.error),
    
    // Getters
    bots,
    lastRefreshed,
    hasPendingJobs: computed(() => bots.value.some(bot => bot.status.isPending)),

    // Actions
    setError,
    setBots,
    setLastRefreshed,
  };
});

export default useBotsStore;
