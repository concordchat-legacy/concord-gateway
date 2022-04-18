import asyncio
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
    retry_on_timeout=True,
)
if os.name != 'nt':
    pool.connection_class = redis.UnixDomainSocketConnection
manager = redis.Redis(connection_pool=pool)
pubsub = manager.pubsub()

# TODO: Complete
def handle_event(d: dict):
    try:
        d = orjson.loads(d['data'])
    except KeyError:
        return

    if d['type'] == 1:
        for sid in sessions:
            if sid._user['id'] == d['data']['user_id']:
                d['data']['t'] = f'USER_{str(d["name"])}'
                asyncio.create_task(sid.send(d['data']))

    elif d['type'] == 2:
        if d.get('user_id'):
            for sid in sessions:
                if sid._user['id'] == d['data']['user_id']:
                    d['data']['t'] = f'GUILD_CREATE'
                    asyncio.create_task(sid.send(d['data']))
                    sid.joined_guilds.append(d['guild_id'])
        else:
            for sid in sessions:
                if d['guild_id'] in sid.joined_guilds:
                    d['data']['t'] = f'GUILD_{str(d["name"])}'
                    asyncio.create_task(sid.send(d['data']))

    elif d['type'] == 3:
        if d.get('guild_id'):
            channel = ...


async def start():
    await pubsub.subscribe(gateway=handle_event)
