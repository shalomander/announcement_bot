import asyncio

import pypros.ctlr as ctlr
import pypros.ipros as ipros
from pypros.log import log
from pypros.packet import Request

ipros.G_incoming_handlers['ctlr'] = ctlr.incoming_handler

async def send(svcname: str, key: bytes, msg: int, data: bytes, timeout = 5):
    if svcname not in ipros.G_maps:
        await ctlr.subscribe(svcname)

    return await ipros.send(svcname, Request(key, msg, data), timeout)
    
async def listen(ip, port, request_cb):
    ipros.SvcSettings.by_svcname('ctlr').auto_reconnect = True
    ipros.SvcSettings.by_svcname('ctlr').greeting_request = lambda: ctlr.join_request(ip, port)
    server = ipros.Server(request_cb)
    await ctlr.join(ip, port)
    return await asyncio.start_server(server, ip, port)
