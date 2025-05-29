import type { Bot, Job, BotStatus, StatusConfig } from '@/types';

const STATUS_CONFIG: StatusConfig = {
  running: { text: 'Running', severity: 'success', isRunning: true },
  stopped: { text: 'Not Running', severity: 'danger', isRunning: false },
  pending: { text: 'Starting...', severity: 'info', isRunning: false },
  error: { text: 'Error', severity: 'danger', isRunning: false },
  failed: { text: 'Failed', severity: 'danger', isRunning: false },
  unknown: { text: 'Unknown', severity: 'danger', isRunning: false },
};

export const useBotStatus = () => {

  /**
   * Creates a status object based on the job status
   */
  const createStatusFromJob = (statusLong: string): BotStatus => {
    const statusLower = statusLong.toLowerCase();
    let state: BotStatus['state'];
    
    if (statusLower.includes("pod in 'pending' phase")) {
      state = 'pending';
    } else if (statusLower.includes("pod in 'running' phase")) {
      state = 'running';
    } else if (statusLower.includes('error') || statusLower.includes('failed')) {
      state = 'error';
    } else {
      state = 'stopped';
    }

    return {
      state,
      ...STATUS_CONFIG[state],
      isPending: state === 'pending',
    };
  };

  /**
   * Updates bots with job status information
   * @param bots - The array of bots to update
   * @param jobs - The array of jobs to get status from
   * @returns Updated array of bots with job status
   */
  const updateBotsWithJobStatus = (bots: Bot[], jobs: Job[]): Bot[] => {
    return bots.map(bot => {
      const matchingJob = jobs.find(job => 
        (job.cmd?.includes(bot.type) || job.name === bot.type)
      );

      if (!matchingJob) {
        return {
          ...bot,
          status: {
            ...bot.status,
            ...STATUS_CONFIG.stopped,
            state: 'stopped',
            isPending: false,
          },
          jobName: ''
        };
      }

      return {
        ...bot,
        status: {
          ...bot.status,
          ...createStatusFromJob(matchingJob.status_long)
        },
        jobName: matchingJob.name || ''
      };
    });
  };

  return {
    updateBotsWithJobStatus,
    statusConfig: STATUS_CONFIG
  };
};

export default useBotStatus;
