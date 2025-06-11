import { Hono, type Context } from 'hono'

const https = await import('node:https')

const TOOLFORGE_API_URL =
  process.env['TOOL_TOOLFORGE_API_URL'] || 'https://api.svc.tools.eqiad1.wikimedia.cloud:30003'

interface JobConfig {
  name: string
  cmd: string
  imagename: string
  continuous?: boolean
  cpu?: string
  emails?: string
  filelog?: boolean
  filelog_stderr?: string
  filelog_stdout?: string
  memory?: string
  mount?: string
  port?: number
  replicas?: number
  retry?: number
  schedule?: string
  timeout?: number
}

interface ToolforgeErrorResponse {
  error: string
  status: number
}

type ToolforgeResponse<T = Record<string, unknown>> = T | ToolforgeErrorResponse

// Helper function to handle API responses
const handleApiResponse = <T extends object>(
  c: Context,
  result: ToolforgeResponse<T>,
  successStatus = 200
) => {
  if (result && typeof result === 'object' && !('error' in result)) {
    // @ts-ignore
    return c.json(result as T, successStatus)
  }

  return c.json({ error: (result as ToolforgeErrorResponse).error }, 500)
}

async function makeToolforgeRequest<T = Record<string, unknown>>(
  method: 'get' | 'post' | 'delete',
  path: string,
  jsonData?: object
): Promise<ToolforgeResponse<T>> {
  const homeDir = process.env['TOOL_DATA_DIR'] || '.'
  const certPath = `${homeDir}/.toolskube/client.crt`
  const keyPath = `${homeDir}/.toolskube/client.key`
  const url = `${TOOLFORGE_API_URL}${path}`

  // Read client certificate and key
  const cert = await Bun.file(certPath).text() // fs.readFile(certPath, 'utf8')
  const key = await Bun.file(keyPath).text() // fs.readFile(keyPath, 'utf8')

  // Create HTTPS agent with client certificates
  const httpsAgent = new https.Agent({
    cert,
    key,
    rejectUnauthorized: false,
  })

  const response = await fetch(url, {
    method: method.toUpperCase(),
    headers: {
      'Content-Type': 'application/json',
    },
    body: jsonData ? JSON.stringify(jsonData) : undefined,
    // @ts-ignore - Node's fetch doesn't have proper types for agent yet
    agent: httpsAgent,
  })

  if (!response.ok) {
    const errorText = await response.text()
    return {
      error: `Toolforge API request failed: ${response.statusText} - ${errorText}`,
      status: response.status,
    }
  }

  return (await response.json()) as T
}

// Authentication middleware
const requireAuth = async (c: Context, next: () => Promise<void>): Promise<Response | void> => {
  const session = c.get('session')
  const accessToken = session.get('access_token')
  const expiresAt = session.get('expires_at')

  if (!accessToken) {
    return c.json({ error: 'Authentication required' }, 401)
  }

  if (expiresAt && Date.now() >= expiresAt * 1000) {
    return c.json({ error: 'Session expired' }, 401)
  }

  return await next()
}

const toolforge = new Hono()

// Get all jobs for a tool
toolforge.get('/jobs/v1/tool/:toolName/jobs', async (c) => {
  const toolName = c.req.param('toolName')
  const result = await makeToolforgeRequest('get', `/jobs/v1/tool/${toolName}/jobs/`)

  return handleApiResponse(c, result)
})

// Create a new job for a tool
toolforge.post('/jobs/v1/tool/:toolName/jobs', requireAuth, async (c) => {
  const toolName = c.req.param('toolName')
  const jobConfig: JobConfig = await c.req.json()

  // Validate required fields
  if (!jobConfig.name || !jobConfig.cmd || !jobConfig.imagename) {
    return c.json({ error: 'Missing required fields: name, cmd, and imagename are required' }, 400)
  }

  const result = await makeToolforgeRequest('post', `/jobs/v1/tool/${toolName}/jobs/`, jobConfig)

  return handleApiResponse(c, result, 201)
})

// Delete a job
toolforge.delete('/jobs/v1/tool/:toolName/jobs/:jobId', requireAuth, async (c) => {
  const { toolName, jobId } = c.req.param()
  const result = await makeToolforgeRequest('delete', `/jobs/v1/tool/${toolName}/jobs/${jobId}`)

  return handleApiResponse(c, result)
})

export default toolforge
