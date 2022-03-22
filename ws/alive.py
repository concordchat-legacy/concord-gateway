import asyncio
import logging
import zlib
import orjson
import ulid
import os
import dotenv
import websockets.server
from typing import Sequence, Any
from .db import users

_log = logging.getLogger(__name__)
dotenv.load_dotenv()

def yield_chunks(input_list: Sequence[Any], chunk_size: int):
    for idx in range(0, len(input_list), chunk_size):
        yield input_list[idx : idx + chunk_size]

class Connection:
    def __init__(self, ws: websockets.server.WebSocketServerProtocol, compress: str, fut: asyncio.Future):
        self.ws = ws
        self.compress = compress
        self.fut = fut
        self.zctx = zlib.compressobj() # could be more optimization here.

    async def _check_session_id(self):
        u = await users.find_one({'session_ids': [self._session_id]})
        if u == None:
            await self.ws.close(4003, 'Invalid Session ID')
            self.fut.set_result(None)
            return
        u.pop('password')
        self._user = u

    async def _send_chunks(self, d: bytes, size: int):
        _log.debug(f'conn:{self.ws.id.__str__()}:{d}, {size}')

        await self.ws.send(yield_chunks(d, size))

    async def _zlib_stream_send(self, encoded):
        d1 = self.zctx.compress(encoded)
        d2 = self.zctx.flush(zlib.Z_SYNC_FLUSH)
        d = d1 + d2

        _log.debug(f'conn:{self.ws.id}:{len(d)}')
        await self._send_chunks(d, 1024)
    
    async def send(self, d: dict):
        d['_trace'] = [f'factions-ws-{str(os.getenv("mode", "prd"))}-' + str(os.getenv('id', '0'))]
        data = orjson.dumps(d)
        await self._zlib_stream_send(data)

    async def _process_recv(self, recv: dict):
        if not isinstance(recv, dict):
            return
        op = recv['op']
        d = recv['d']

    async def ready(self):
        await self.send({
            'op': 0,
            't': 'READY',
            'd': self._user
        })

    async def recv(self):
        while not self.ws.closed:
            d = await self.ws.recv()
            await self._process_recv(orjson.loads(d))

    async def run(self, d: dict):
        data = orjson.loads(d)

        if not isinstance(data, dict):
            return await self.ws.close(4001, 'Invalid Data Sent')

        try:
            self._session_id = data['session_id']
            self.session_id = ulid.new()
        except KeyError:
            return await self.ws.close(4002, 'No session_id Given')

        await self._check_session_id()

        await self.ready()
        await self.recv()
