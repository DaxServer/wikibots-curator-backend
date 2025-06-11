<script setup lang="ts">
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import BotActions from '@/components/BotActions.vue'
import { useBotsStore } from '@/stores/bots.store'

interface Props {
  handleStartJob: (jobType: string) => void
  handleDeleteJob: (jobType: string) => void
}

const props = defineProps<Props>()
const botsStore = useBotsStore()
</script>

<template>
  <DataTable
    :value="botsStore.bots"
    :loading="botsStore.loading"
    stripedRows
    size="small"
    class="p-datatable-sm"
  >
    <Column
      field="type"
      header="Type"
    >
      <template #body="{ data }">
        <span
          v-if="data?.type"
          class="font-bold"
        >
          {{ data.type }}
        </span>
        <span
          v-else
          class="text-gray-400 italic"
        >
          Unknown
        </span>
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

    <Column
      field="jobName"
      header="Job"
    >
      <template #body="{ data }">
        <span
          v-if="data?.jobName"
          class="font-mono text-sm"
        >
          {{ data.jobName }}
        </span>
      </template>
    </Column>

    <Column header="Command">
      <template #body="{ data }">
        <code class="text-sm">
          {{ data.command }}{{ data.args ? ' ' + data.args.join(' ') : '' }}
        </code>
      </template>
    </Column>

    <Column header="Actions">
      <template #body="{ data }">
        <BotActions
          :bot="data"
          :on-start="props.handleStartJob"
          :on-stop="props.handleDeleteJob"
        />
      </template>
    </Column>
  </DataTable>
</template>
