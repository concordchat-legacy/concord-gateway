import asyncio
import sys
import websockets.server
import os
import http
import dotenv
import logging
import orjson
from server.redis_pubsub import start
from server.core import ws_handler
from server.db import connect

loop = asyncio.new_event_loop()
logging.basicConfig(level=logging.DEBUG)
dotenv.load_dotenv()

try:
    import uvloop # type: ignore
    uvloop.install()
except(ImportError, ModuleNotFoundError):
    pass

async def process_request(path, head):
    if path == '/__development/ping':
        return http.HTTPStatus.OK, [], orjson.dumps({'message': 'pong!', 'code': 0})

async def startup():
    if os.name != 'nt':
        await websockets.server.unix_serve(
            ws_handler=ws_handler,
            host='0.0.0.0',
            port=int(os.getenv('port', 5000)),
            ping_interval=1,
            ping_timeout=30,
            process_request=process_request
        )
    else:
        await websockets.server.serve(
            ws_handler=ws_handler,
            host='0.0.0.0',
            port=int(os.getenv('port', 5000)),
            ping_interval=4,
            ping_timeout=45,
            process_request=process_request
        )
    await start()
    print('Connected to redis, now connecting to cassandra', file=sys.stderr)
    connect()
    f = asyncio.Future()
    await f

asyncio.run(startup())