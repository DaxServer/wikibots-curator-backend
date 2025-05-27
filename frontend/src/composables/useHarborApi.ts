import type {BuildPackMetadata, ImageArtifact, ImageArtifactTag} from '@/types/harbor';
import useHarborStore from "@/stores/harbor.store.ts";

/**
 * Fetches and extracts processes from the latest Harbor artifact
 * @returns Promise<void>
 * @throws {Error} If there's an error fetching or processing the artifact
 */
export const useHarborApi = () => {
  const harborStore = useHarborStore();

  /**
   * Fetches processes from the latest Harbor artifact
   * @returns Promise<void>
   */
  const fetchProcessesFromHarbor = async (): Promise<void> => {
    try {
      harborStore.setLoading(true);
      harborStore.setError('');

      // Fetch all artifacts from Harbor
      const response = await fetch('/harbor-api/projects/tool-curator/repositories/wikibots/artifacts?with_tag=true&with_label=true');

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.message || `Failed to fetch image artifacts: ${response.statusText}`;
        harborStore.setError(errorMsg);
        throw new Error(errorMsg);
      }

      const artifacts = await response.json();

      // Find the latest artifact by tag
      const latestArtifact = artifacts.find((artifact: ImageArtifact) =>
        artifact.tags?.some((tag: ImageArtifactTag) => tag.name === 'latest')
      );

      if (!latestArtifact) {
        harborStore.setError('No latest artifact found');
        throw new Error('No latest artifact found');
      }

      // Extract build metadata
      const buildMetadataString = latestArtifact.extra_attrs?.config?.Labels?.['io.buildpacks.build.metadata'];

      if (!buildMetadataString) {
        harborStore.setError('No build metadata found in the latest artifact');
        throw new Error('No build metadata found in the latest artifact');
      }

      // Parse and return processes
      const buildMetadata = JSON.parse(buildMetadataString) as BuildPackMetadata;

      harborStore.setProcesses(buildMetadata.processes);
    } finally {
      harborStore.setLoading(false);
    }
  };

  return { fetchProcessesFromHarbor };
};

export default useHarborApi;
