import asyncio
import sys
import aioredis as redis
import os
import dotenv
import orjson
from .alive import sessions
from .db import Member

dotenv.load_dotenv()

pool = redis.ConnectionPool(
    host=os.getenv('redis_uri'),
    port=os.getenv('redis_port'),
    password=os.getenv('redis_password'),
    db=int(os.getenv('redis_db', 0)),
    retry_on_timeout=True
)
if os.name != 'nt':
    pool.connection_class = redis.UnixDomainSocketConnection
manager = redis.Redis(connection_pool=pool)
pubsub = manager.pubsub()

def _send_guild_event(d: dict):
    if isinstance(d['data'], bytes):
        c = orjson.loads(d['data'])
        if c.get('presence', False):
            ms = Member.objects(Member.id == c['member_id']).allow_filtering()
            guild_ids = []

            for m in ms:
                guild_ids.append(m.guild_id)

            for sid in sessions:
                for id in guild_ids:
                    if id in sid or id == c['d']['id']:
                        c.pop('member_id')
                        c.pop('presence')
                        asyncio.create_task(sid.send(c))
                        break

def _send_user_event(*args, **kwargs):
    pass

async def start():
    await pubsub.subscribe(GUILD_EVENTS=_send_guild_event, USER_EVENTS=_send_user_event)
