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
import logging
import os
import sys

import aiohttp.web as aiohttp
import dotenv

from gateway.core import ws_handler
from gateway.db import connect
from gateway.incoming import start

loop = asyncio.new_event_loop()
logging.basicConfig(level=logging.DEBUG)
dotenv.load_dotenv()

try:
    import uvloop  # type: ignore

    uvloop.install()
except (ImportError, ModuleNotFoundError):
    pass


async def startup():
    await start()

connect()
app = aiohttp.Application(debug=True)
app.add_routes([aiohttp.get('/', ws_handler)])
loop = asyncio.new_event_loop()
loop.create_task(startup())
aiohttp.run_app(
    app=app,
    host='0.0.0.0',
    port=int(os.getenv('PORT'), 5000),
    loop=loop,
)
loop.run_forever()
