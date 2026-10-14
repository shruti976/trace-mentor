"""Same-origin lifecycle endpoint and Streamlit HTTP/WebSocket gateway."""
import asyncio,base64,hashlib,hmac,json,os,subprocess,sys,time
from aiohttp import web,ClientSession,WSMsgType
from config import ADMIN_ACCESS_TOKEN,read_setting
import v5_store as s

def signing_key():
    value=read_setting('V5_EVENT_SECRET') or ADMIN_ACCESS_TOKEN
    if not value: raise RuntimeError('V5_EVENT_SECRET or ADMIN_ACCESS_TOKEN is required for browser event authentication')
    return value.encode()
def token(pid,period,deadline):
    payload=base64.urlsafe_b64encode(json.dumps({'participant_id':pid,'period':period,'release_id':s.spec.RELEASE_ID,'expires':s.dt(deadline).timestamp()+60},sort_keys=True).encode()).decode()
    return payload+'.'+hmac.new(signing_key(),payload.encode(),hashlib.sha256).hexdigest()
def verify(value):
    payload,sig=value.split('.',1)
    if not hmac.compare_digest(sig,hmac.new(signing_key(),payload.encode(),hashlib.sha256).hexdigest()): raise ValueError('Invalid token')
    data=json.loads(base64.urlsafe_b64decode(payload))
    if data['expires']<time.time() or data['release_id']!=s.spec.RELEASE_ID: raise ValueError('Expired token')
    return data
async def events(request):
    # Same-origin only. Token is in the POST body, never an URL or access log.
    origin=request.headers.get('Origin')
    if origin and origin.split('://')[-1]!=request.host: raise web.HTTPForbidden()
    try:
        body=await request.json(); claim=verify(body['token'])
        session=await asyncio.to_thread(s.consultation,claim['participant_id'],claim['period'],body['action'],body['tab'],body['client_event_id'])
        return web.json_response({'accepted':True,'consultation_session_id':session})
    except (ValueError,KeyError,TypeError): return web.json_response({'accepted':False},status=409)
async def proxy(request):
    session=request.app['client'];url='http://127.0.0.1:8501'+request.rel_url.path_qs
    headers={k:v for k,v in request.headers.items() if k.lower() not in ('host','content-length','connection','upgrade','sec-websocket-key','sec-websocket-version','sec-websocket-extensions','sec-websocket-protocol')}
    # Preserve the public host so Streamlit can validate the browser Origin.
    headers['Host']=request.host
    if request.headers.get('Upgrade','').lower()=='websocket':
        protocols=tuple(x.strip() for x in request.headers.get('Sec-WebSocket-Protocol','').split(',') if x.strip())
        async with session.ws_connect(url,headers=headers,protocols=protocols,max_msg_size=64*1024*1024) as upstream:
            downstream=web.WebSocketResponse(protocols=protocols,max_msg_size=64*1024*1024);await downstream.prepare(request)
            async def pipe(src,dst):
                async for msg in src:
                    if msg.type==WSMsgType.TEXT:await dst.send_str(msg.data)
                    elif msg.type==WSMsgType.BINARY:await dst.send_bytes(msg.data)
                    else:break
                await dst.close()
            await asyncio.gather(pipe(upstream,downstream),pipe(downstream,upstream));return downstream
    async with session.request(request.method,url,headers=headers,data=await request.read(),allow_redirects=False) as response:
        clean={k:v for k,v in response.headers.items() if k.lower() not in ('content-encoding','transfer-encoding','content-length','connection')}
        return web.Response(status=response.status,headers=clean,body=await response.read())
async def lifecycle(app):
    app['client']=ClientSession()
    for attempt in range(120):
        try:
            async with app['client'].get('http://127.0.0.1:8501/_stcore/health') as response:
                if response.status==200: break
        except OSError: pass
        await asyncio.sleep(.5)
    else:
        await app['client'].close()
        raise RuntimeError('Streamlit did not become ready')
    yield
    await app['client'].close()
def main():
    signing_key()
    child=subprocess.Popen([sys.executable,'-m','streamlit','run','app.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false'])
    app=web.Application(client_max_size=4*1024*1024);app.cleanup_ctx.append(lifecycle)
    app.router.add_post('/study-events/v5',events);app.router.add_route('*','/{tail:.*}',proxy)
    try:web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','8502')),access_log=None)
    finally:child.terminate();child.wait(timeout=15)
if __name__=='__main__':main()
