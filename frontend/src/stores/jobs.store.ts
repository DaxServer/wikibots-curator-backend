import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Job } from '@/types';

export const useJobsStore = defineStore('jobs', () => {
  // State
  const loading = ref(false);
  const error = ref('');
  const jobs = ref<Job[]>([]);
  const starting = ref<Record<string, boolean>>({});
  const deleting = ref<Record<string, boolean>>({});

  // Getters
  const hasJobs = computed(() => jobs.value.length > 0);

  // Actions
  const setLoading = (isLoading: boolean) => {
    loading.value = isLoading;
  };

  const setError = (errorMessage: string) => {
    error.value = errorMessage;
  };

  const setJobs = (newJobs: Job[]) => {
    jobs.value = newJobs;
  };

  const setStarting = (jobName: string, isStarting: boolean) => {
    if (isStarting) {
      starting.value[jobName] = true;
    } else {
      delete starting.value[jobName];
    }
  };

  const setDeleting = (jobName: string, isDeleting: boolean) => {
    if (isDeleting) {
      deleting.value[jobName] = true;
    } else {
      delete deleting.value[jobName];
    }
  };

  return {
    // State
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    jobs: computed(() => jobs.value),
    starting: computed(() => starting.value),
    deleting: computed(() => deleting.value),
    
    // Getters
    hasJobs,
    
    // Actions
    setLoading,
    setError,
    setJobs,
    setStarting,
    setDeleting,
  };
});

export default useJobsStore;
