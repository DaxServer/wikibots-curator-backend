import type { Bot, BotWithStatus, Job, StatusSeverity } from '@/types';

type StatusConfig = {
  [key: string]: {
    long: string;
    severity: StatusSeverity;
  };
};

const STATUS_CONFIG: StatusConfig = {
  running: { long: 'Running', severity: 'success' as StatusSeverity },
  active: { long: 'Active', severity: 'success' as StatusSeverity },
  stopped: { long: 'Not Running', severity: 'danger' as StatusSeverity },
  'not running': { long: 'Not Running', severity: 'danger' as StatusSeverity },
  error: { long: 'Error', severity: 'danger' as StatusSeverity },
  failed: { long: 'Failed', severity: 'danger' as StatusSeverity },
  unknown: { long: 'Unknown', severity: 'info' as StatusSeverity },
};

export const useBotStatus = () => {
  /**
   * Determines the severity of a bot's status for UI display
   * @param status - The status of the bot
   * @returns A severity level for UI display
   */
  const getStatusSeverity = (status: string): StatusSeverity => {
    return STATUS_CONFIG[status.toLowerCase()]?.severity || STATUS_CONFIG.unknown.severity;
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
        (job.cmd?.includes(bot.type) || job.name === bot.type) &&
        job.status_long
      );

      const isRunning = matchingJob?.status_long.toLowerCase().includes("state 'running'") ?? false;
      
      return {
        ...bot,
        isRunning,
        status: isRunning ? 'running' : 'stopped',
        jobName: matchingJob?.name || ''
      };
    });
  };

  /**
   * Maps bots to include status information
   * @param bots - The array of bots to process
   * @returns Array of bots with enriched status data
   */
  const botsWithStatus = (bots: Bot[]): BotWithStatus[] => {
    return bots.map(bot => {
      const statusLower = bot.status.toLowerCase();
      const statusInfo = STATUS_CONFIG[statusLower] || STATUS_CONFIG.unknown;

      return {
        ...bot,
        status: bot.status,
        statusLong: statusInfo.long,
        statusSeverity: statusInfo.severity
      };
    });
  };

  return {
    getStatusSeverity,
    updateBotsWithJobStatus,
    botsWithStatus
  };
};

export default useBotStatus;
