import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { logger } from 'hono/logger'
import { showRoutes } from 'hono/dev'
import { trimTrailingSlash } from 'hono/trailing-slash'
import { proxy } from 'hono/proxy'
import { sessionMiddleware, CookieStore } from 'hono-sessions'
import { serveStatic } from 'hono/bun'
import auth from './routes/auth'
import harbor from './routes/harbor'
import toolforge from './routes/toolforge'

declare module 'bun' {
  interface Env {
    PORT?: string
  }
}

const isProduction = Bun.env?.NODE_ENV !== 'production'

// Session configuration
export const sessionConfig = {
  secret: Bun.randomUUIDv7(),
  maxAge: 60 * 60 * 24 * 7, // 1 week in seconds
  cookie: {
    name: 'session',
    path: '/',
    httpOnly: true,
    secure: isProduction,
    sameSite: 'lax' as const,
  },
  store: new CookieStore(),
  encryptionKey: Bun.randomUUIDv7(),
}

// Create a new Hono app with strict routing
const app = new Hono({ strict: true })

// Middleware
app.use('*', logger())

// Session middleware
app.use('*', sessionMiddleware(sessionConfig))

// Handle trailing slashes
app.use('*', trimTrailingSlash())

app.use(
  '*',
  cors({
    origin: process.env['CORS_ORIGIN'] || 'http://localhost:5173',
    allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'Authorization'],
    credentials: true, // Allow credentials (cookies, authorization headers, etc.)
    exposeHeaders: ['Set-Cookie'], // Expose the Set-Cookie header
  })
)

// Mount routes
app.route('/auth', auth)
app.route('/api/harbor', harbor)
app.route('/api/toolforge', toolforge)

// Serve frontend in production
if (isProduction) {
  // Serve static files from the frontend dist directory
  const frontendDistDir = `${__dirname}/../../frontend/dist`
  app.get('/', (c) => c.html(Bun.file(`${frontendDistDir}/index.html`).text()))
  app.use('/assets/*', serveStatic({ root: frontendDistDir }))
} else {
  // In development, proxy all requests to the Vite dev server
  app.all('*', (c) => {
    return proxy('http://localhost:8000', {
      ...c.req,
      headers: {
        ...c.req.header(),
        'X-Forwarded-For': '127.0.0.1',
        'X-Forwarded-Host': c.req.header('host'),
      },
    })
  })
}

// Start the server
const port = parseInt(Bun.env?.PORT || '8000')

showRoutes(app, {
  verbose: true,
})

export default {
  port,
  fetch: app.fetch,
}
