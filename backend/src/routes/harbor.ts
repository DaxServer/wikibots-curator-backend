import { Hono } from 'hono'
import { HTTPException } from 'hono/http-exception'

const HARBOR_API_URL =
  'https://tools-harbor.wmcloud.org/api/v2.0/projects/tool-curator/repositories/wikibots/artifacts'

const harbor = new Hono()

interface ImageArtifactTag {
  name: string
}

interface ImageArtifact {
  tags?: ImageArtifactTag[]
  extra_attrs?: {
    config?: {
      Labels?: {
        'io.buildpacks.build.metadata'?: string
        [key: string]: unknown
      }
    }
    [key: string]: unknown
  }
  digest?: string
}

interface BuildPackProcess {
  type: string
  command: string
  args: string[]
  direct: boolean
}

interface BuildPackMetadata {
  processes: BuildPackProcess[]
}

async function getLatestArtifact(): Promise<ImageArtifact> {
  const params = new URLSearchParams({
    with_tag: 'true',
    with_label: 'true',
  })

  const response = await fetch(`${HARBOR_API_URL}?${params.toString()}`)

  if (!response.ok) {
    throw new HTTPException(500, {
      message: `Failed to fetch from Harbor: ${response.statusText}`,
    })
  }

  const artifacts = (await response.json()) as ImageArtifact[]

  // Find the latest artifact by tag
  const latestArtifact = artifacts.find((artifact) =>
    artifact.tags?.some((tag) => tag.name === 'latest')
  )

  if (!latestArtifact) {
    throw new HTTPException(404, { message: 'No latest artifact found' })
  }

  return latestArtifact
}

harbor.get('/processes', async (c) => {
  const latestArtifact = await getLatestArtifact()

  // Extract build metadata
  const buildMetadataStr =
    latestArtifact.extra_attrs?.config?.Labels?.['io.buildpacks.build.metadata']

  if (!buildMetadataStr) {
    throw new HTTPException(404, { message: 'No build metadata found in the latest artifact' })
  }

  const buildMetadata = JSON.parse(buildMetadataStr) as BuildPackMetadata
  return c.json(buildMetadata.processes, 200)
})

export default harbor
