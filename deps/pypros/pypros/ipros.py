import asyncio
import struct
from contextlib import suppress

from pypros.alias import Alias
from pypros.map import Map
from pypros.packet import Request, Reply, Packet, ServiceMessages, compose_reply
from pypros.IO import IStream, OStream
from pypros.log import log
import pypros.icrc

G_self_alias = None
G_maps = {}
G_conns = {}
G_incoming_handlers = {}
G_reconnect_period = 1

class SvcSettings:
    G_settings = {}

    def __init__(self):
        self.auto_reconnect = False
        self.greeting_request = None

    @classmethod
    def by_svcname(cls, svcname: str):
        if svcname not in cls.G_settings:
            cls.G_settings[svcname] = SvcSettings()
        return cls.G_settings[svcname]

class ConnFlags:
    KEY     = 0x0001
    STATUS  = 0x0002
    REPLY2  = 0x0004
    CTLRCNG = 0x0800

class Conn:
    max_queue_size = 10
    default_flags = ConnFlags.KEY | ConnFlags.STATUS | ConnFlags.REPLY2 | ConnFlags.CTLRCNG

    def __init__(self, host, port, alias=None):
        self.pending = {}
        self.host = host
        self.port = port
        if isinstance(alias, str):
            alias = Alias(alias)
        self.alias = alias
        self.reader = None
        self.reader_coro = None
        self.writer = None

        self.queue = asyncio.Queue(Conn.max_queue_size)
        self.writer_coro = asyncio.get_event_loop().create_task(Conn._do_write(self, self.queue))

    async def send(self, req, timeout) -> Reply:
        if self.queue.full():
            return Reply(500, '{} queue overflow'.format(self), None)

        if req.noreply:
            return await self.queue.put(req)

        self.pending[req.sync] = asyncio.get_event_loop().create_future()
        try:
            await self.queue.put(req)
            resp = await asyncio.wait_for(self.pending[req.sync], timeout)
        except asyncio.TimeoutError:
            log.error('request timeout {}'.format(req))
            resp = Reply(500, 'timeout', None)
            self._request_done(req.sync, resp)
        return resp

    def closed(self):
        if self.writer_coro.done():
            return True
        if self.writer and self.writer.transport.is_closing():
            return True
        return False

    async def shutdown(self):
        if self.alias and self.alias.svc and SvcSettings.by_svcname(self.alias.svc).auto_reconnect:
            asyncio.get_event_loop().create_task(reconnect(self.host, self.port, self.alias))
        if self.writer:
            self.writer.close()
        self.writer_coro.cancel()
        if self.reader_coro:
            self.reader_coro.cancel()
        with suppress(asyncio.CancelledError):
            await self.writer_coro
            if self.reader_coro:
                await self.reader_coro

    async def reply(self, req: Packet, status, reason, data = None):
        if data is None:
            data = b''
        return await self.send(compose_reply(req, status, reason, data), 0)

    async def _do_write(self, queue):
        try:
            global G_self_alias
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.reader_coro = asyncio.get_event_loop().create_task(Conn._do_read(self))
            self.writer.write(Packet.hello(G_self_alias, Conn.default_flags).dump())

            while True:
                req = await queue.get()
                log.debug('<= {} {}'.format(self, req))
                self.writer.write(req.dump())
        except asyncio.CancelledError:
            log.warn('{} writer shutdown'.format(self))
            raise
        except OSError as x:
            log.error('{} writer OS error: {}'.format(self, x))
        except Exception as x:
            log.exception('{} writer failure: {}'.format(self, x))
        finally:
            syncs = list(self.pending.keys())
            for sync in syncs:
                self._request_done(sync, Reply(500, 'cancelled', None))
            await self.shutdown()

    async def _do_read(self):
        try:
            while True:
                p = await read_packet(self.reader)
                if p is None:
                    log.warn('Connection closed by peer {}'.format(self))
                    return await self.shutdown()
                asyncio.get_event_loop().create_task(self._process(p))
        except asyncio.CancelledError:
            log.warn('{} reader shutdown'.format(self))
            raise
        except OSError as x:
            log.error('{} reader error: {}'.format(self, x))
        except struct.error as x:
            log.exception('protocol error with {}'.format(self))
            await self.shutdown()
        except Exception as x:
            log.exception('{} reader failure: {}'.format(self, x))

    async def _process(self, p):
        log.debug('=> {} {}'.format(self, p))
        if p.msg == ServiceMessages.REPLY:
            self._request_done(p.sync, Reply.from_packet(p))
        if p.msg == ServiceMessages.HELLO:
            self.alias = Alias.load(IStream(p.body).getLps())
            log.info('HELLO from {}'.format(self.alias))
        elif self.alias and self.alias.svc in G_incoming_handlers:
            await G_incoming_handlers[self.alias.svc](self, p)

    def __repr__(self):
        if self.alias:
            return repr(self.alias)
        return '{}:{}'.format(self.host, self.port)

    def _request_done(self, sync, rep: Reply):
        if sync in self.pending:
            fut = self.pending[sync]
            if not fut.done():
                fut.set_result(rep)
            del self.pending[sync]
        else:
            log.error('unexpected reply {} from {}'.format(sync, self))

async def read_packet(r):
    hdr = await r.read(12)
    if hdr == bytes():
        return None
    msg, len, sync = IStream(hdr).getIproHdr()
    body = await r.read(len)
    return Packet(msg, sync, body)


class IncomingRequest:
    def __init__(self, req: Packet, sender: Alias, writer):
        self.req = req
        self.sender = sender
        self.writer = writer

    def __repr__(self):
        return '=> {} {}'.format(self.sender, self.req)

    def reply(self, status, reason, data = None):
        self.writer.write(compose_reply(self.req, status, reason, data).dump())

class Server:
    def __init__(self, request_cb):
        self.request_cb = request_cb

    async def __call__(self, reader, writer):
        peer = 'someone'
        try:
            writer.write(Packet.hello(G_self_alias, Conn.default_flags).dump())
            hello = await read_packet(reader)
            peer = Alias.load(IStream(hello.body).getLps())
            log.info('{} connected'.format(peer))
            while True:
                p = await read_packet(reader)
                if p is None:
                    break
                asyncio.get_event_loop().create_task(self.request_cb(IncomingRequest(p, peer, writer)))
        finally:
            log.info('{} disconnected'.format(peer))



def reset_map(svcname, new_map: Map):
    G_maps.pop(svcname, None)
    G_maps[svcname] = new_map

def reset_self_alias(s):
    global G_self_alias
    G_self_alias = Alias(s)
    log.info('self: {}'.format(G_self_alias))

def self_alias():
    assert(G_self_alias)
    return G_self_alias

async def connection(host, port, alias=None):
    hostport = '{}:{}'.format(host, port)
    if hostport not in G_conns or G_conns[hostport].closed():
        G_conns[hostport] = Conn(host, port, alias)
        if alias and alias.svc and SvcSettings.by_svcname(alias.svc).greeting_request:
            await G_conns[hostport].send(SvcSettings.by_svcname(alias.svc).greeting_request(), 5)

    return G_conns[hostport]

async def send(svcname, req: Request, timeout: int) -> Reply:
    srv = select_srv_by_key(svcname, req.key)
    cn = await connection(srv.host, srv.port, srv.alias)
    return await cn.send(req, timeout)

async def sendto(host, port, req: Request, timeout: int) -> Reply:
    cn = await connection(host, port)
    return await cn.send(req, timeout)

async def send_noreply(svcname, req: Request):
    req.noreply = True
    srv = select_srv_by_key(svcname, req.key)
    cn = await connection(srv.host, srv.port, srv.alias)
    return await cn.send(req, 0)

def select_srv_by_key(svcname: str, key: bytes):
    global G_maps
    if svcname not in G_maps:
        raise Exception('{} uninit'.format(svcname))
    return G_maps[svcname].srv_by_bkr(pypros.icrc.calc(key))

async def shutdown():
    await asyncio.gather(*[conn.shutdown() for _, conn in G_conns.items()])

async def reconnect(host, port, alias):
    await asyncio.sleep(G_reconnect_period)
    await connection(host, port, alias)
