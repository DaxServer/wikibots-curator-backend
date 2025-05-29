<script setup lang="ts">
// Vue
import { computed, onMounted, ref } from 'vue';

// Components
import BotActions from './BotActions.vue';

// PrimeVue Components
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Button from 'primevue/button';
import Tag from 'primevue/tag';
import Message from 'primevue/message';

// Stores
import { useJobsStore } from '@/stores/jobs.store';
import { useHarborStore } from '@/stores/harbor.store.ts';
import { useBotsStore } from '@/stores/bots.store';

// Composables
import useBotsApi from "@/composables/useBotsApi.ts";
import useJobsApi from "@/composables/useJobsApi.ts";

// Initialize stores and composables
const jobsStore = useJobsStore();
const harborStore = useHarborStore();
const botsStore = useBotsStore();

const { fetchBots, fetchJobs, startPolling } = useBotsApi();
const { startJob, deleteJob } = useJobsApi();

// Local state
const isRefreshing = ref(false);

// Computed properties
const isLoading = computed(() => harborStore.loading || jobsStore.loading || isRefreshing.value);
const error = computed(() => {
  if (botsStore.error) return botsStore.error;
  if (jobsStore.error) return jobsStore.error;
  if (harborStore.error) return harborStore.error;
  return '';
});

/**
 * Handles refreshing bots data and/or performing job actions
 * @param actionOrEvent - Either an async function to execute before refreshing or a MouseEvent
 */
const refreshBots = async (actionOrEvent?: (() => Promise<void>) | MouseEvent) => {
  // Handle the case where the function is called from a click event
  const action = typeof actionOrEvent === 'function' ? actionOrEvent : undefined;

  try {
    isRefreshing.value = true;
    
    // Execute the provided action if any
    if (action) {
      await action();
      // After a job action, we need to refresh jobs to get the latest status
      await fetchJobs();
    } else {
      // If no action provided, just refresh the bots data
      await fetchBots();
    }

    // Start polling if there are pending jobs
    if (botsStore.hasPendingJobs) {
      startPolling();
    }
  } finally {
    botsStore.setLastRefreshed();
    isRefreshing.value = false;
  }
};

// Initialize data when component is mounted
onMounted(() => {
  refreshBots();
});

// Wrapper functions for job actions
const handleStartJob = (jobType: string) => refreshBots(() => startJob(jobType));
const handleDeleteJob = (jobType: string) => refreshBots(() => deleteJob(jobType));
</script>

<template>
  <div class="card mt-4">
    <div class="flex justify-between items-center mb-4">
      <h2 class="m-0">Bots</h2>
      <div class="flex items-center gap-2">
        <span class="text-sm text-gray-600">
          Last updated: {{ botsStore.lastRefreshed?.toLocaleTimeString() ?? 'Never' }}
        </span>
        <Button
          icon="pi pi-refresh"
          class="p-button-rounded p-button-info"
          :loading="isRefreshing"
          :disabled="isLoading"
          @click="refreshBots"
        />
      </div>
    </div>

    <!-- Error Message -->
    <Message v-if="error" severity="error" class="mb-4" :closable="false">
      {{ error }}
    </Message>

    <!-- Data Table -->
    <DataTable
      v-else
      :value="botsStore.bots"
      :loading="isLoading"
      stripedRows
      size="small"
      class="p-datatable-sm"
    >
      <Column field="type" header="Type">
        <template #body="{ data }">
          <span v-if="data?.type" class="font-bold">{{ data.type }}</span>
          <span v-else class="text-gray-400 italic">Unknown</span>
        </template>
      </Column>

      <Column header="Status">
        <template #body="{ data }">
          <Tag
            :value="data.status.text"
            :severity="data.status.severity"
          />
        </template>
      </Column>

      <Column field="jobName" header="Job">
        <template #body="{ data }">
          <span v-if="data?.jobName" class="font-mono text-sm">{{ data.jobName }}</span>
        </template>
      </Column>

      <Column header="Command">
        <template #body="{ data }">
          <code class="text-sm">{{ data.command }}{{ data.args ? ' ' + data.args.join(' ') : '' }}</code>
        </template>
      </Column>

      <Column header="Actions">
        <template #body="{ data }">
          <BotActions
            :bot="data"
            :on-start="handleStartJob"
            :on-stop="handleDeleteJob"
          />
        </template>
      </Column>
    </DataTable>
  </div>
</template>
