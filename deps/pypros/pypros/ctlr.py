import pypros.ipros as ipros
from pypros.packet import Request, Packet
from pypros.map import Map, Record
from pypros.log import log
from pypros.alias import Alias
from pypros.IO import IStream, OStream
import git

import asyncio

G_cur_role = None
G_map_received = {}
role_changed_cb = None
G_git_hash = 'unknown'
try:
    G_git_hash = git.Repo(search_parent_directories=True).head.object.hexsha
except:
    log.error('Dude you gotta run that from GIT repo, otherwise I have no hash to send to ctlr')

def _hp(h, p): return '{}:{}'.format(h,p)

class MsgId:
    UNDEF    = 0
    GETMAP   = 1
    SBC      = 2
    JOINOLD  = 3
    MAP      = 4
    PREP     = 5
    MIGR     = 6
    MOVEDOLD = 7
    FLIP     = 8
    FLOP     = 9
    JOIN     =10
    CHECK    =11
    PING     =12
    KILL     =13
    FLIPCHK  =14
    READY    =15
    MOVED    =16
    FORK     =17

class JoinTag:
    NONE        = 0
    ASSIGNED    = 1
    MASTER      = 2
    SLAVE       = 3
    MOVEDOLD    = 4
    FLIP        = 5
    FLOP        = 6
    SRV         = 7
    FLAG        = 8
    HASH        = 9
    READY       =10
    START       =11
    MOVED       =12
    SYNC        =13
    COMPOT      =14

class SrvFlag:
    CHECK     = 0x00000001
    PING      = 0x00000002
    KILL      = 0x00000004
    DROP      = 0x00000008
    FORK      = 0x00000010

G_join_flags = SrvFlag.CHECK | SrvFlag.PING | SrvFlag.KILL


def init(self_alias, host, port):
    ipros.reset_self_alias(self_alias)
    m = Map()
    m.append(Record(0, host, port, Alias('ctlr.unknown.ctlr')))
    ipros.reset_map('ctlr', m)

async def subscribe(svcname, timeout = 5):
    log.info('subscribe to {}'.format(svcname))
    if svcname in G_map_received:
        return await asyncio.wait_for(G_map_received[svcname].wait(), timeout)

    G_map_received[svcname] = asyncio.Event()
    try:
        resp = await ipros.send('ctlr', Request(svcname, MsgId.SBC, ''), 3)
        if resp.status != 200:
            raise Exception('Failed to subscribe to {} map: {}'.format(svcname, resp))
        await asyncio.wait_for(G_map_received[svcname].wait(), timeout)
    except asyncio.TimeoutError:
        log.error('timeout waiting for {} map'.format(svcname))
        raise
    finally:
        del G_map_received[svcname]

def join_request(ip, port):
    alias = ipros.self_alias()
    ostr = OStream()
    ostr.putIPv4(ip)
    ostr.putU16n(port)

    ostr.putTlv(JoinTag.HASH, G_git_hash)
    ostr.putTlvU32(JoinTag.FLAG, G_join_flags)
    ostr.putTlvU32(JoinTag.READY, 1)
    rq = Request(alias.svc, MsgId.JOIN, ostr.data)
    rq.key_prepend = False
    return rq

async def join(ip, port):
    return await ipros.send('ctlr', join_request(ip, port), 3)

async def flop(dst: Alias):
    pkt = OStream()
    pkt.putLps(dst.dump())
    r = Request('', MsgId.FLOP, pkt.data)
    r.key_prepend = False
    return await ipros.send('ctlr', r, 3)

class IncomingHandlers:
    @staticmethod
    async def MAP(cn, p):
        istr = IStream(p.body)
        mapname = str(istr.getLps().getAll(), encoding='utf8')
        m = Map(istr)
        m.dump_to(log.debug, 'ctlr: got new map for {}'.format(mapname))
        ipros.reset_map(mapname, m)
        if mapname in G_map_received:
            G_map_received[mapname].set()

        global G_cur_role
        me = m.srv_by_alias(ipros.self_alias())
        if me and me.role != G_cur_role:
            if role_changed_cb:
                role_changed_cb(G_cur_role, me.role)
            G_cur_role = me.role

    @staticmethod
    async def PING(cn, p):
        return await ipros.send('ctlr', Request('', MsgId.PING, ''), 5)

    @staticmethod
    async def FLIP(cn, p):
        if len(p.body) == 0:
            log.error('abort flip')
            return

        dst = Alias.load(IStream(p.body).getLps())
        log.warn('start flip to {}'.format(dst))
        await cn.reply(p, 200, 'ok');
        return await flop(dst)

async def incoming_handler(cn: ipros.Conn, p: Packet):
    for methname in dir(MsgId):
        if getattr(MsgId, methname) == p.msg:
            cb = getattr(IncomingHandlers, methname, None)
            if cb:
                await cb(cn, p)

