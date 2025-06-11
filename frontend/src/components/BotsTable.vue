<script setup lang="ts">
// Vue
import { computed, onMounted } from 'vue'

// PrimeVue Components
import Button from 'primevue/button'
import Message from 'primevue/message'

// Components
import BotsDataTable from '@/components/BotsDataTable.vue'

// Stores
import { useJobsStore } from '@/stores/jobs.store'
import { useHarborStore } from '@/stores/harbor.store'
import { useBotsStore } from '@/stores/bots.store'

// Composables
import useBotsApi from '@/composables/useBotsApi'
import useJobsApi from '@/composables/useJobsApi'

// Initialize stores and composables
const jobsStore = useJobsStore()
const harborStore = useHarborStore()
const botsStore = useBotsStore()

const { fetchBots, fetchJobs } = useBotsApi()
const { startJob, deleteJob } = useJobsApi()

// Computed properties
const error = computed(() => {
  const errors = []
  if (botsStore.error) errors.push(botsStore.error)
  if (jobsStore.error) errors.push(jobsStore.error)
  if (harborStore.error) errors.push(harborStore.error)
  return errors.join('\n')
})

/**
 * Handles executing a job action and refreshing job data.
 */
const handleJobAction = async (action: () => Promise<void>) => {
  await action()
  await fetchJobs()
}

/**
 * Refreshes bots data and starts polling if there are pending jobs.
 */
const refreshBotsData = async () => {
  await fetchBots()
}

/**
 * Handles refreshing bots data and/or performing job actions
 * @param actionOrEvent - Either an async function to execute before refreshing or a MouseEvent
 */
const refreshBots = async (actionOrEvent?: (() => Promise<void>) | MouseEvent) => {
  const action = typeof actionOrEvent === 'function' ? actionOrEvent : undefined

  try {
    botsStore.setLoading(true)

    if (action) {
      await handleJobAction(action)
    } else {
      await refreshBotsData()
    }
  } finally {
    botsStore.setLastRefreshed()
    botsStore.setLoading(false)
  }
}

// Initialize data when component is mounted
onMounted(() => {
  refreshBots()
})

// Wrapper functions for job actions
const handleStartJob = (jobType: string) => refreshBots(() => startJob(jobType))
const handleDeleteJob = (jobType: string) => refreshBots(() => deleteJob(jobType))
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
          :loading="botsStore.loading"
          :disabled="botsStore.loading"
          @click="refreshBots"
        />
      </div>
    </div>

    <!-- Error Message -->
    <Message
      v-if="error"
      severity="error"
      class="mb-4"
      :closable="false"
    >
      {{ error }}
    </Message>

    <!-- Data Table -->
    <BotsDataTable
      v-else
      :handle-start-job="handleStartJob"
      :handle-delete-job="handleDeleteJob"
    />
  </div>
</template>
