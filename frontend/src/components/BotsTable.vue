<script setup lang="ts">
// Vue
import { computed, onMounted, ref } from 'vue';

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

const { fetchBots } = useBotsApi();
const { startJob, deleteJob } = useJobsApi();

// Local state
const isRefreshing = ref(false);
const lastRefreshed = ref<Date | null>(null);

// Computed properties
const isLoading = computed(() => botsStore.loading || jobsStore.loading || harborStore.loading || isRefreshing.value);
const error = computed(() => {
  if (botsStore.error) return botsStore.error;
  if (jobsStore.error) return jobsStore.error;
  if (harborStore.error) return harborStore.error;
  return '';
});

// Handle refreshing bots data
const refreshBots = async () => {
  try {
    isRefreshing.value = true;
    await fetchBots();
    lastRefreshed.value = new Date();
  } finally {
    isRefreshing.value = false;
  }
};

// Initialize data when component is mounted
onMounted(() => {
  refreshBots();
});
</script>

<template>
  <div class="card mt-4">
    <div class="flex justify-between items-center mb-4">
      <h2 class="m-0">Bots</h2>
      <div class="flex items-center gap-2">
        <span class="text-sm text-gray-600">
          Last updated: {{ lastRefreshed?.toLocaleTimeString() ?? 'Never' }}
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
            v-if="data?.statusLong && data?.statusSeverity"
            :value="data.statusLong"
            :severity="data.statusSeverity"
            :class="{'p-tag-rounded': true}"
          />
          <span v-else class="text-gray-400 italic">Unknown</span>
        </template>
      </Column>

      <Column field="jobName" header="Job">
        <template #body="{ data }">
          <span v-if="data?.jobName" class="font-mono text-sm">{{ data.jobName }}</span>
          <span v-else class="text-gray-400 italic">-</span>
        </template>
      </Column>

      <Column header="Command">
        <template #body="{ data }">
          <code class="text-sm">{{ data.command }}{{ data.args ? ' ' + data.args.join(' ') : '' }}</code>
        </template>
      </Column>

      <Column header="Actions" :exportable="false">
        <template #body="{ data }">
          <div class="flex gap-2">
            <Button
              v-if="!data.isRunning"
              type="button"
              class="p-button-sm p-button-info"
              @click="startJob(data.type)"
            >
              <i class="pi pi-play mr-2"></i>
              <span>Start</span>
            </Button>
            <Button
              v-else
              type="button"
              class="p-button-sm p-button-danger"
              @click="deleteJob(data.type)"
            >
              <i class="pi pi-stop mr-2"></i>
              <span>Stop</span>
            </Button>
          </div>
        </template>
      </Column>
    </DataTable>
  </div>
</template>
