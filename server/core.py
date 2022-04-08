import urllib.parse
import asyncio
from websockets import server
from .alive import Connection

async def ws_handler(ws: server.WebSocketServerProtocol, url):
    while True:
        d = await ws.recv()
        break

    args = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

    try:
        compress = args['compress'][0]
    except(IndexError, KeyError):
        compress = 'zlib-stream'

    if compress not in ('zlib-stream', 'zstd-stream'):
        return await ws.close(reason='Invalid Compress Type')

    fut = asyncio.Future()
    conn = Connection(ws, compress, fut)
    await conn.run(d)
    await fut
