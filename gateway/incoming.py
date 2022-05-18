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
import os
import sys

import dotenv
import orjson
import redis.asyncio as redis

from .alive import sessions

dotenv.load_dotenv()

pool = redis.ConnectionPool(
    host=os.getenv('redis_uri'),
    port=os.getenv('redis_port'),
    password=os.getenv('redis_password'),
    db=int(os.getenv('redis_db', 0)),
    retry_on_timeout=True,
)
manager = redis.Redis(connection_pool=pool)
pubsub = manager.pubsub()

# TODO: Complete
def handle_event(d: dict):
    try:
        d = orjson.loads(d['data'])
    except KeyError:
        return

    print(
        f'Processing Data for event {str(d["data"]["t"])}: {str(d["data"])}',
        file=sys.stderr,
    )

    if d['type'] == 1:
        d['data']['t'] = f'USER_{str(d["name"])}'
        for sid in sessions:
            if sid._user['id'] == d['data']['user_id']:
                asyncio.create_task(sid.send(d['data']))

    elif d['type'] == 2:
        if d.get('user_id'):
            d['data']['t'] = f'GUILD_CREATE'
            for sid in sessions:
                if sid._user['id'] == d['data']['user_id']:
                    asyncio.create_task(sid.send(d['data']))
                    sid.joined_guilds.append(d['guild_id'])
        else:
            d['data']['t'] = f'GUILD_{str(d["name"])}'
            for sid in sessions:
                if d['guild_id'] in sid.joined_guilds:
                    asyncio.create_task(sid.send(d['data']))

                    if d['name'] == 'JOIN':
                        sid.joined_guilds.append(d['guild_id'])
                    elif d['name'] == 'DELETE':
                        sid.joined_guilds.remove(d['guild_id'])

    elif d['type'] == 3:
        d['data']['t'] = (
            f'CHANNEL_{str(d["name"])}'
            if not d['is_message']
            else f'MESSAGE_{str(d["name"])}'
        )
        if d.get('guild_id'):
            for sid in sessions:
                if d['guild_id'] in sid.joined_guilds:
                    if d['is_message']:
                        if sid.intents.guild_messages:
                            asyncio.create_task(sid.send(d['data']))
                    else:
                        if sid.intents.guild_channels:
                            asyncio.create_task(sid.send(d['data']))
        else:
            recipients = d['channel']['recipients']

            for sid in sessions:
                for recipient in recipients:
                    if sid._user['id'] == recipient['id']:
                        if sid.intents.direct_messages:
                            asyncio.create_task(sid.send(d['data']))

    elif d['type'] == 5:
        for sid in sessions:
            if sid._user['id'] == d['receiver_id']:
                d['data']['t'] = 'FRIEND_REQUEST'
                asyncio.create_task(sid.send(d['data']))
            elif sid._user['id'] == d['requester_id']:
                asyncio.create_task(sid.send({'t': 'FRIEND_ACK', 'd': None}))

    elif d['type'] == 6:
        d['data']['t'] = f'MEMBER_{str(d["name"])}'
        for sid in sessions:
            if d['guild_id'] in sid.joined_guilds:
                if sid.intents.guild_members:
                    asyncio.create_task(sid.send(d['data']))

    elif d['type'] == 7:
        d['data']['t'] = 'PRESENCE_UPDATE'
        for sid in sessions:
            if sid._user['id'] == d['user_id']:
                guilds = sid.joined_guilds
                break

        for sid in sessions:
            for guild in guilds:
                if guild in sid.joined_guilds:
                    if sid.intents.presences:
                        asyncio.create_task(sid.send(d['data']))


async def start():
    await pubsub.subscribe(gateway=handle_event)
