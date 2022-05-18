# Copyright 2021 Concord, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
import hashlib
import logging
import os
import sys
import threading
import zlib
from time import time
from typing import Any, List, Sequence

import aiohttp.web as aiohttp
import redis.asyncio as redis
import cassandra.cqlengine.query
import dotenv
import orjson
from cassandra.cqlengine.connection import get_session

from .db import Presence, to_dict
from .intents import Intents
from .tokens import verify_token

_log = logging.getLogger(__name__)
dotenv.load_dotenv()
sessions: List['Connection'] = []

pool = redis.ConnectionPool(
    host=os.getenv('redis_uri'),
    port=os.getenv('redis_port'),
    password=os.getenv('redis_password'),
    db=int(os.getenv('redis_db', 0)),
    retry_on_timeout=True,
)
manager = redis.Redis(connection_pool=pool)
pubsub = manager.pubsub()


def yield_chunks(input_list: Sequence[Any], chunk_size: int):
    for idx in range(0, len(input_list), chunk_size):
        yield input_list[idx : idx + chunk_size]


class Connection:
    def __init__(
        self,
        ws: aiohttp.WebSocketResponse,
        fut: asyncio.Future,
    ):
        self.ws = ws
        self.fut = fut
        self.zctx = zlib.compressobj()  # could be more optimization here.
        self.intents: Intents = None
        self.hb_fut: asyncio.Future = None
        self.joined_guilds: List[int] = []
        self.gave_heartbeat: bool = False
        self.requests_given: int = 0
        self.last_request = time()

    @classmethod
    def get_session_id(self):
        return hashlib.sha1(os.urandom(128)).hexdigest()

    async def _check_session_id(self):
        try:
            u = verify_token(self._session_id)
        except (ValueError):
            await self.ws.close(code=4003, message='Invalid Session ID')
            self.fut.set_result(None)
            self._user = None
            return
        u.pop('password')
        u.pop('verification_code')
        self._user = u

    async def send_guilds(self):
        objs = get_session().execute(
            'SELECT * FROM members WHERE id = {};'.format(str(self._user['id']))
        )

        guilds: List[dict] = []

        for obj in objs:
            guilds.append(
                to_dict(
                    get_session().execute(
                        'SELECT * FROM guilds WHERE id = {};'.format(obj['guild_id'])
                        ).one()
                    )
                )

        for guild in guilds:
            self.joined_guilds.append(guild['id'])
            if self.intents.guilds:
                await self.send(guild)

        del guilds
        del objs

    async def _send_chunks(self, d: bytes, size: int):
        _log.debug(f'conn:{self.session_id}:{d}, {size}')
        if isinstance(d, bytes):
            d = d.decode()

        await self.ws.send_str(d)

    async def _zlib_stream_send(self, encoded: bytes):
        # d1 = self.zctx.compress(encoded)
        # d2 = self.zctx.flush(zlib.Z_SYNC_FLUSH)
        # d = d1 + d2

        _log.debug(f'conn:{self.session_id}:{encoded.decode()}')

        # NOTE: Maybe raise the amount of chunks?
        await self._send_chunks(encoded, 1024)

    async def send(self, d: dict):
        data = {}
        data['op'] = 1

        data['d'] = d
        data['_trace'] = [
            f'concord-{os.getenv("cluster", "asia-east1")}-gateway-{str(os.getenv("mode", "dev"))}-'
            + str(threading.current_thread().ident or 0)
        ]
        data['_trace'] = str(data['_trace'])
        data = orjson.dumps(data)

        # create a separate task to let the node do other stuff aswell
        asyncio.create_task(self._zlib_stream_send(data))

    def make_event_ready(self, *, name: str, d: dict, **extra):
        data = {}

        data['t'] = name
        data['d'] = d
        for k, v in extra.items():
            data[k] = v

        return data

    async def cleanup_presence(self):
        if self.presence.status == 'offline':
            return

        self.presence.update(status='offline')

        model = to_dict(self.presence)

        model.pop('stay_offline')

        await manager.publish('gateway', orjson.dumps({'data': model, 'user_id': self._user['id']}))

    async def ready(self):
        await self.send(
            self._user
        )

        try:
            query: Presence = Presence.get(Presence.user_id == self._user['id'])
        except (cassandra.cqlengine.query.DoesNotExist):
            p: Presence = Presence.create(
                user_id=self._user['id'],
                since=time(),
                status='online',
                afk=False,
            )

            redis_p = to_dict(p)

            d = self.make_event_ready(
                name='PRESENCE_UPDATE', d=redis_p, member_id=p.user_id, presence=True
            )

            # NOTE: Not sure if the event will be given to the port since it published it,
            # although it should
            await manager.publish('GUILD_EVENTS', orjson.dumps(d).decode())
        else:
            query2 = to_dict(query)

            if query2['stay_offline'] is True:
                # ignore, the user is offline on purpose.
                return
            else:
                query.update(status='online')

            query2.pop('stay_offline')

            d = self.make_event_ready(
                name='PRESENCE_UPDATE', d=query2, member_id=query.user_id, presence=True
            )

            await manager.publish(
                'gateway', orjson.dumps({'user_id': self._user['id'], 'data': query2})
            )

            # saves a db request, although this *might* somewhat increase ram
            self.presence: Presence = query

            await asyncio.sleep(0.1)

        await self.send_guilds()

    async def check_close(self):
        if self.ws.closed:
            sessions.remove(self)  # remove the session before changing presence
            await self.cleanup_presence()
            self.fut.set_result(None)
            del self
            return

        await asyncio.sleep(45)
        loop = asyncio.get_running_loop()
        loop.create_task(self.check_close())

    async def recv(self):
        await self.ws.receive()
        self.requests_given += 1

        if time() - self.last_request > 60:
            self.requests_given = 0

        self.last_request = time()

        if self.requests_given > 60:
            await self.ws.close(
                code=4008,
                message='Too Many Requests'
            )
            self.fut.set_result(None)

    async def reset_hb(self):
        await asyncio.sleep()

    async def run(self, d: dict):
        data = orjson.loads(d)

        if not isinstance(data, dict):
            return await self.ws.close(4001, 'Invalid Data Sent')

        try:
            self._session_id: str = data['token']
            self.session_id = self.get_session_id()
        except KeyError:
            return await self.ws.close(4002, 'No session_id Given')

        sessions.append(self)

        if data.get('intents'):
            self.intents = Intents(int(data['intents']))
        else:
            self.intents = Intents(0)

        await self._check_session_id()

        await self.ready()

        await self.check_close()
