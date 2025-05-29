<script setup lang="ts">
import { computed } from 'vue';
import { useJobsStore } from '@/stores/jobs.store';
import type { Bot } from '@/types';

const props = defineProps<{
  bot: Bot;
  onStart: (jobType: string) => void;
  onStop: (jobType: string) => void;
}>();

const jobsStore = useJobsStore();

const isLoading = computed(() => 
  jobsStore.starting[props.bot.type] || jobsStore.deleting[props.bot.type]
);
</script>

<template>
  <div class="flex gap-2">
    <Button
      v-if="!bot.status.isRunning && !bot.status.isPending"
      severity="info"
      label="Start"
      icon="pi pi-play"
      size="small"
      :loading="jobsStore.starting[bot.type]"
      :disabled="isLoading"
      @click="onStart(bot.type)"
    />
    <Button
      v-else-if="bot.status.isRunning"
      severity="danger"
      size="small"
      icon="pi pi-stop"
      label="Stop"
      :loading="jobsStore.deleting[bot.type]"
      :disabled="isLoading"
      @click="onStop(bot.type)"
    />
    <Tag
      v-else-if="bot.status.isPending"
      severity="info"
      size="small"
      icon="pi pi-spin pi-spinner"
      value="Starting..."
    />
    <Tag
      v-else
      severity="danger"
      size="small"
      icon="pi pi-question"
      value="Unknown"
    />
  </div>
</template>
