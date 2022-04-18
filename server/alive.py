import asyncio
import logging
import sys
import zlib
import orjson
import hashlib
import os
import dotenv
import cassandra.cqlengine.query
import websockets.server
import websockets.exceptions
from datetime import datetime, timezone
from typing import List, Sequence, Any, Union
from .db import User, Presence, Guild, Member, Activity, to_dict
from .intents import Intents
from .redis_pubsub import manager

_log = logging.getLogger(__name__)
dotenv.load_dotenv()
sessions: List['Connection'] = []


def yield_chunks(input_list: Sequence[Any], chunk_size: int):
    for idx in range(0, len(input_list), chunk_size):
        yield input_list[idx : idx + chunk_size]


class Connection:
    def __init__(
        self,
        ws: websockets.server.WebSocketServerProtocol,
        compress: str,
        fut: asyncio.Future,
    ):
        self.ws = ws
        self.compress = compress
        self.fut = fut
        self.zctx = zlib.compressobj()  # could be more optimization here.
        self.intents: Intents = None
        self.hb_fut: asyncio.Future = None
        self.joined_guilds: List[int] = []

    @classmethod
    def get_session_id(self):
        return hashlib.sha1(os.urandom(128)).hexdigest()

    async def _check_session_id(self):
        try:
            objs: User = User.objects().allow_filtering()
            u = objs.get(session_ids__contains=self._session_id)
        except (cassandra.cqlengine.query.DoesNotExist):
            await self.ws.close(4003, 'Invalid Session ID')
            self.fut.set_result(None)
            self._user = None
            return
        u = to_dict(u)
        u.pop('password')
        self._user = u

    async def send_from_intents(self, event_name: str, data: dict):
        if event_name.startswith('DIRECT_MESSAGE'):
            if self.intents.direct_messages:
                await self.send({'t': event_name, 'd': data})
        elif event_name.startswith('MESSAGE'):
            if self.intents.guild_messages:
                await self.send({'t': event_name, 'd': data})
        elif event_name.startswith('GUILD_') and 'MEMBER' not in event_name:
            if self.intents.guilds:
                # TODO: Limit to Guild
                await self.send({'t': event_name, 'd': data})
        elif event_name.startswith('PRESENCE'):
            if self.intents.presences:
                # TODO: Limit to Guild
                data.pop('member_id')
                data.pop('presence')
                await self.send({'t': event_name, 'd': data})

    async def send_guilds(self):
        objs = Member.objects(Member.id == self._user['id'])

        guilds: List[dict] = []

        for obj in objs:
            guilds.append(to_dict(Guild.get(id=obj['guild_id'])))

        for guild in guilds:
            self.joined_guilds.append(guild['id'])
            if self.intents.guilds:
                await self.send(guild)

        del guilds
        del objs

    async def _send_chunks(self, d: bytes, size: int):
        _log.debug(f'conn:{self.ws.id.__str__()}:{d}, {size}')

        await self.ws.send(yield_chunks(d, size))

    async def _zlib_stream_send(self, encoded):
        d1 = self.zctx.compress(encoded)
        d2 = self.zctx.flush(zlib.Z_SYNC_FLUSH)
        d = d1 + d2

        _log.debug(f'conn:{self.ws.id}:{len(d)}')

        # NOTE: Maybe raise the amount of chunks?
        await self._send_chunks(d, 1024)

    async def send(self, d: dict):
        d['_trace'] = [
            f'concord-{os.getenv("cluster", "asia-east1")}-gateway-{str(os.getenv("mode", "dev"))}-'
            + os.getenv('node', '0')
        ]
        data = orjson.dumps(d)
        # create a separate task to let the node do other stuff aswell
        asyncio.create_task(self._zlib_stream_send(data))

    async def _process_recv(self, recv: dict):
        if not isinstance(recv, dict):
            return

        op = int(recv['op'])
        d: Union[int, dict] = recv['d']

        if op == 1:
            ...

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

        model.pop('no_online')

        d = self.make_event_ready(
            name='PRESENCE_UPDATE', d=model, member_id=self.presence.id, presence=True
        )

        await manager.publish('GUILD_EVENTS', orjson.dumps(d).decode())

    async def ready(self):
        await self.send(
            {
                'op': 0,
                't': 'READY',
                'd': self._user,
            }
        )

        try:
            query: Presence = Presence.get(Presence.id == self._user['id'])
        except (cassandra.cqlengine.query.DoesNotExist):
            p: Presence = Presence.create(
                id=self._user['id'],
                since=None,
                activity=Activity(
                    name='',
                    type=0,
                    created_at=datetime.now(timezone.utc),
                    emoji=None,
                    buttons=None,
                ),
                status='online',
                afk=False,
            )

            redis_p = to_dict(p)

            d = self.make_event_ready(
                name='PRESENCE_UPDATE', d=redis_p, member_id=p.id, presence=True
            )

            # NOTE: Not sure if the event will be given to the port since it published it,
            # although it should
            await manager.publish('GUILD_EVENTS', orjson.dumps(d).decode())
        else:
            query2 = to_dict(query)

            if query2['no_online'] == True:
                # ignore, the user is offline on purpose.
                return
            else:
                query.update(status='online')

            query2.pop('no_online')

            d = self.make_event_ready(
                name='PRESENCE_UPDATE', d=query2, member_id=query.id, presence=True
            )

            await manager.publish('GUILD_EVENTS', orjson.dumps(d).decode())

            # saves a db request, although this *might* somewhat increase ram
            self.presence: Presence = query

            await asyncio.sleep(0.1)

            await self.send(d)

        await self.send_guilds()

    async def recv(self):
        while not self.ws.closed:
            d = await self.ws.recv()
            await self._process_recv(orjson.loads(d))

    async def run(self, d: dict):
        data = orjson.loads(d)

        if not isinstance(data, dict):
            return await self.ws.close(4001, 'Invalid Data Sent')

        try:
            self._session_id: str = data['session_id']
        except KeyError:
            return await self.ws.close(4002, 'No session_id Given')

        try:
            sessions.append(self)

            if data.get('intents'):
                self.intents = Intents(int(data['intents']))
            else:
                self.intents = Intents(0)

            await self._check_session_id()

            await self.ready()

            await self.recv()

            sessions.remove(self)
        except Exception as exc:
            print(exc, file=sys.stderr)
            sessions.remove(self)  # remove the session before changing presence
            await self.cleanup_presence()
            self.fut.set_result(None)
            del self
