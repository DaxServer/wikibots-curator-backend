from mwoauth import ConsumerToken, Handshaker, RequestToken
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import os

router = APIRouter(prefix="/auth", tags=["auth"])

consumer_token = ConsumerToken(
    os.environ.get('OAUTH_CLIENT_ID'),
    os.environ.get('OAUTH_CLIENT_SECRET')
)

handshaker = Handshaker(
    "https://commons.wikimedia.org/w/index.php",
    consumer_token,
    user_agent='Curator / Toolforge curator.toolforge.org / Wikimedia Commons User:DaxServer'
)

@router.get('/login')
async def login(request: Request):
    redirect, request_token = handshaker.initiate()
    request.session['request_token'] = request_token
    return RedirectResponse(url=redirect)


@router.get('/callback')
async def auth(request: Request):
    if 'request_token' not in request.session:
        return HTMLResponse('No request token in session', status_code=400)

    request_token = RequestToken(
        key=request.session['request_token'][0],
        secret=request.session['request_token'][1],
    )
    response_qs = str(request.url).split('?', 1)[-1]

    try:
        access_token = handshaker.complete(request_token, response_qs)
        identity = handshaker.identify(access_token)
        request.session['user'] = dict(identity)
        return RedirectResponse(url=router.url_path_for('whoami'))
    except Exception as e:
        return HTMLResponse(f'Authentication failed: {e}', status_code=500)


@router.get('/logout')
async def logout(request: Request):
    request.session.pop('user', None)
    request.session.pop('request_token', None)
    return RedirectResponse(url='/')


@router.get('/whoami', name='whoami')
async def whoami(request: Request):
    user = request.session.get('user')
    if user:
        return user
    return JSONResponse({'message': 'Not authenticated'}, status_code=401)
