# Copyright 2021 Concord, Inc.
# See LICENSE for more information.
import asyncio

from aiohttp import WSMsgType as wsmtype
from aiohttp.web import Request, WebSocketResponse

from .alive import Connection, sessions


async def ws_handler(request: Request):
    spool = WebSocketResponse(timeout=45)
    await spool.prepare(request=request)
    d = None

    try:
        msg = await spool.receive(timeout=300)
    except:
        await spool.close(code=4005)
        return

    if msg.type != wsmtype.TEXT:
        await spool.close(code=4005)

    d = msg.data

    try:
        fut = asyncio.Future()
        conn = Connection(spool, fut=fut)
        await conn.run(d)
        await fut
    except:
        sessions.remove(conn)  # remove the session before changing presence
        await conn.cleanup_presence()
        try:
            fut.set_result(None)
        except:
            pass
        del conn

    return spool
