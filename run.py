import websockets.server
import os
import http
import dotenv
import logging
import orjson
from ws.core import ws_handler
from ws.db import loop

logging.basicConfig(level=logging.DEBUG)
dotenv.load_dotenv()

try:
    import uvloop # type: ignore
    uvloop.install()
except(ImportError, ModuleNotFoundError):
    pass

async def process_request(path, head):
    if path == '/_dev/ping':
        return http.HTTPStatus.OK, [], orjson.dumps({'message': 'pong!', 'code': 0})

async def startup():
    await websockets.server.serve(
        ws_handler=ws_handler,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        ping_interval=5,
        ping_timeout=30,
        process_request=process_request
    )

loop.create_task(startup())
loop.run_forever()