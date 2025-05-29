import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Process } from '@/types';

export const useHarborStore = defineStore('harbor', () => {
  // State
  const loading = ref(false);
  const error = ref('');
  const processes = ref<Process[]>([]);

  // Getters
  const hasProcesses = computed(() => processes.value.length > 0);

  // Actions
  const setLoading = (isLoading: boolean) => {
    loading.value = isLoading;
  };

  const setError = (errorMessage: string) => {
    error.value = errorMessage;
  };

  const setProcesses = (newProcesses: Process[]) => {
    processes.value = newProcesses;
  };

  return {
    // State
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    processes: computed(() => processes.value),

    // Getters
    hasProcesses,

    // Actions
    setLoading,
    setError,
    setProcesses,
  };
});

export default useHarborStore;
