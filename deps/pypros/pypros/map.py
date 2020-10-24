import bisect
from pypros.IO import IStream
from pypros.log import log
from pypros.alias import Alias

class Record:
    def __init__(self, bkr_start: int, host: str, port: int, alias: Alias):
        self.bkr_start = bkr_start
        self.host = host
        self.port = port
        self.hostport = '{}:{}'.format(self.host, self.port)
        self.alias = alias

    def __repr__(self):
        return '{:08x}    {}'.format(self.bkr_start, self.alias)

class Tag:
    MAP_TYPE = 1
    MAP_NODE = 2
    MAP_SRV  = 3
    MAP_BKRS = 4
    NODE_NAME = 1
    SRV_BIND = 1
    SRV_ROLE = 2
    SRV_NODE = 3

class Role:
    NONE        = 0
    MAIN        = 1
    SLAVE       = 2
    MIRROR      = 3
    FALLBACK    = 4
    AB          = 5
    DUP         = 6
    BOND        = 7
    FORK        = 8
    REPL        = 9

    @classmethod
    def by_id(cls, id):
        for n in cls.__dict__:
            if getattr(cls, n) == id:
                return n.lower()
        raise Exception('unknown srv role: {}'.format(id))

class Node:
    def __init__(self, istr):
        tset = istr.getTlvset()
        self.name = tset[Tag.NODE_NAME].getAll()

class Srv:
    @classmethod
    def none(cls):
        return cls()

    def __init__(self, istr = None):
        self.alias = Alias('none.a.none')
        self.ip = [0,0,0,0]
        self.host = '0.0.0.0'
        self.port = 0
        self.role = 'main'
        self.node_id = -1

        if istr:
            self.alias = Alias(istr.getStr())
            tset = istr.getTlvset()
            self._parse_bind(tset[Tag.SRV_BIND])
            self.role = Role.by_id(tset[Tag.SRV_ROLE].getU32())
            self.node_id = tset[Tag.SRV_NODE].getU32()

    def _parse_bind(self, istr):
        self.ip = istr.getIPv4()
        self.host = '.'.join([str(i) for i in self.ip])
        self.port = istr.getU16n()

    def __repr__(self):
        return '{}/{} ({}) = {}:{}'.format(self.node_id, self.alias, self.role, self.host, self.port)

class Map:
    def __init__(self, istr: IStream = None):
        self.type = ''
        self.node = {}
        self.srv = {}
        self.node_masters = {}
        self.bkrs = []

        if istr:
            istr.tlvForeach({
                Tag.MAP_TYPE: lambda v: setattr(self, 'type', v.getU32()), # Fuck you Python
                Tag.MAP_NODE: lambda v: self._load_node(v),
                Tag.MAP_SRV:  lambda v: self._load_srv(v),
                Tag.MAP_BKRS: lambda v: self._load_bkrs(v),
            })

    def append(self, r: Record):
        assert not self.bkrs and r.bkr_start == 0 or self.bkrs[-1].bkr_start < r.bkr_start
        self.bkrs.append(r)

    def srv_by_bkr(self, key) -> Record:
        keys = [r.bkr_start for r in self.bkrs]
        i = bisect.bisect_right(keys, key)
        if i == 0:
            raise Exception('search in empty map')
        return self.bkrs[i-1]

    def srv_by_alias(self, alias) -> Srv:
        if str(alias) not in self.srv:
            return None
        return self.srv[str(alias)]

    def _load_node(self, v):
        i = v.getU32()
        self.node[i] = Node(v)

    def _load_srv(self, v):
        srv = Srv(v)
        self.srv[str(srv.alias)] = srv
        log.debug('got srv: {}'.format(srv))
        if srv.role == 'main':
            self.node_masters[srv.node_id] = srv

    def _load_bkrs(self, v):
        nbkrs = v.getU64()
        bk = 0
        while v.inAvail():
            node_id = v.getVarInt()
            srv = self.node_masters.get(node_id, Srv.none())
            self.bkrs.append(Record(bk, srv.host, srv.port, srv.alias))
            bk += 1 + v.getMishasFuckingInt()
        assert(bk == 2**32)

    def dump_to(self, writer, prefix = ''):
        s = prefix
        for bkr in self.bkrs:
            s += '\n{}'.format(bkr)
        writer(s)
