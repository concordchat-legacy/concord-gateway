# Copyright 2021 Concord, Inc.
# See LICENSE for more information.
import asyncio
import logging
import os
import sys

import aiohttp.web as aiohttp
import dotenv

from gateway.core import ws_handler
from gateway.db import connect
from gateway.receiver import start

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
