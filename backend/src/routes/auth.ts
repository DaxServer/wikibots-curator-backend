import { Hono } from 'hono'
import type { Session } from 'hono-sessions'

// Type for our session data
type SessionData = {
  access_token: string
  refresh_token: string
  expires_in: number
  expires_at: number
  user: Record<string, unknown>
}

declare module 'hono' {
  interface ContextVariableMap {
    session: Session<SessionData>
  }
}

const auth = new Hono()

// OAuth endpoints
const OAUTH_AUTHORIZE_URL = 'https://meta.wikimedia.org/w/rest.php/oauth2/authorize'
const OAUTH_REQUEST_TOKEN_URL = 'https://meta.wikimedia.org/w/rest.php/oauth2/access_token'
const OAUTH_PROFILE_URL = 'https://meta.wikimedia.org/w/rest.php/oauth2/resource/profile'

// Get OAuth configuration from environment
const OAUTH_CLIENT_ID = <string>Bun.env['OAUTH_CLIENT_ID']
const OAUTH_CLIENT_SECRET = <string>Bun.env['OAUTH_CLIENT_SECRET']

// Login route - initiates OAuth flow
auth.get('/login', (c) => {
  // Generate OAuth parameters
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: OAUTH_CLIENT_ID as string,
  })

  // Redirect to MediaWiki OAuth authorization URL
  const authUrl = new URL(OAUTH_AUTHORIZE_URL)
  authUrl.search = params.toString()

  return c.redirect(authUrl.toString())
})

// Callback route - handles the OAuth 2.0 authorization code
auth.get('/callback', async (c) => {
  const { code } = c.req.query()

  if (!code) {
    throw new Error('Missing authorization code')
  }

  // Exchange the authorization code for an access token
  const tokenResponse = await fetch(OAUTH_REQUEST_TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': 'Curator-Backend/1.0',
      Accept: 'application/json',
    },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code: code,
      client_id: OAUTH_CLIENT_ID,
      client_secret: OAUTH_CLIENT_SECRET,
    }),
  })

  const tokenData = (await tokenResponse.json()) as {
    access_token: string
    refresh_token: string
    expires_in: number
    token_type: string
  }

  if (!tokenData.access_token) {
    throw new Error('Invalid token response: missing access_token')
  }

  // Get user info
  const userResponse = await fetch(OAUTH_PROFILE_URL, {
    headers: {
      Authorization: `Bearer ${tokenData.access_token}`,
      'User-Agent': 'Curator-Backend/1.0',
    },
  })

  const user = (await userResponse.json()) as {
    username?: string
    [key: string]: unknown
  }

  // Calculate expiration time
  const expiresAt = Math.floor(Date.now() / 1000) + tokenData.expires_in

  // Store the access token and user info in the session
  const session = c.get('session')
  session.set('access_token', tokenData.access_token)
  session.set('refresh_token', tokenData.refresh_token)
  session.set('expires_in', tokenData.expires_in)
  session.set('expires_at', expiresAt)
  session.set('user', user)

  return c.redirect('/')
})

// Get current session info
auth.get('/whoami', (c) => {
  const session = c.get('session')
  const accessToken = session.get('access_token')

  if (!accessToken) {
    return c.json(
      {
        authenticated: false,
        message: 'Not authenticated',
      },
      401
    )
  }

  const user = session.get('user') as Record<string, unknown> | undefined
  const username = user?.['username']

  return c.json({
    authenticated: true,
    authorized: process.env['X_USERNAME'] === username,
    username,
  })
})

// Logout route
auth.get('/logout', (c) => {
  const session = c.get('session')
  // Clear all session data
  session.set('access_token', '')
  session.set('refresh_token', '')
  session.set('expires_in', 0)
  session.set('expires_at', 0)
  session.set('user', {})

  // Alternative: Invalidate the session by setting a very short expiration
  // This depends on your session store implementation
  // session.set('expires_at', Math.floor(Date.now() / 1000) - 3600)

  return c.redirect('/')
})

export default auth
