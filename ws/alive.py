import asyncio
import logging
import zlib
import orjson
import ulid
import os
import dotenv
import websockets.server
from typing import List, Sequence, Any
from .db import users

_log = logging.getLogger(__name__)
dotenv.load_dotenv()
sessions: List['Connection'] = []

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
        if u == None and self._session_id != '835040690734891009':
            await self.ws.close(4003, 'Invalid Session ID')
            self.fut.set_result(None)
            self._user = None
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
        d = orjson.loads(recv['d'])

        if op == 100:
            if self._session_id != '835040690734891009':
                return

            user = await users.find_one({'_id': d['id_to']})

            if user == None:
                return

            for s in sessions:
                if s._session_id in user['session_ids']:
                    d.pop('id_to')
                    data = {
                        'op': d.pop('op'),
                        't': d.pop('t'),
                        'd': d,
                    }
                    await self.send(data)

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

        sessions.append(self)

        await self.recv()

        sessions.remove(self)
