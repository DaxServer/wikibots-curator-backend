export interface Bot {
  type: string;
  command: string;
  args: string[];
  isRunning: boolean;
  status: 'running' | 'stopped' | 'error' | 'unknown';
  jobName: string;
}

export type StatusSeverity = 'success' | 'danger' | 'info';

export interface BotWithStatus extends Bot {
  statusLong: string;
  statusSeverity: StatusSeverity;
}
