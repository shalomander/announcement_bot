import struct
import socket
import random
import types
import varint


def parseScheme(istr, scheme):
    if not istr.inAvail():
        return None

    assert(isinstance(scheme, dict))
    ret = {}
    while istr.inAvail():
        t, v = istr.getTlv()
        if t not in scheme:
            continue
        subscheme = scheme[t]
        if isinstance(subscheme, dict):
            ret[t] = parseScheme(v, subscheme)
        elif isinstance(subscheme, list):
            assert(len(subscheme) == 1)
            subscheme = subscheme[0]
            if isinstance(subscheme, dict):
                ret.setdefault(t, []).append(parseScheme(v, subscheme))
            else:
                ret.setdefault(t, []).append(v)
        else:
            ret[t] = v

    return ret


class Rid(object):
    RID_ID_BITS = 56

    def __init__(self, t, i):
        self.type = t
        self.id = i
    def __int__(self):
        return self.id | (self.type << self.RID_ID_BITS)
    def __eq__(self, b):
        return self.id == b.id and self.type == b.type
    def __ne__(self, b):
        return not (self == b)
    def __hash__(self):
        return int(self)
    def __str__(self):
        return str(self.type) + ':' + str(self.id)
    def __repr__(self):
        return str(self)

    @classmethod
    def fromU64(cls, u64):
        i = u64 & ((1 << cls.RID_ID_BITS) - 1)
        t = u64 >> cls.RID_ID_BITS
        return cls(t, i)

    @classmethod
    def getRandomId(cls):
        return int(random.getrandbits(cls.RID_ID_BITS))

    @classmethod
    def nextId(cls, id):
        return (id + 1) % (1 << cls.RID_ID_BITS)


class MsgId(object):
    def __init__(self, u64_or_time, ctr=None):
        self.t = 0
        self.c = 0
        if ctr == None:
            if u64_or_time == -1:
                u64_or_time = 2^64-1
            istr = IStream(OStream().putU64(u64_or_time).data)
            self.c = istr.getU32()
            self.t = istr.getU32()
        else:
            self.c = ctr
            self.t = u64_or_time

    def __hash__(self):
        return int(self)
    def __int__(self):
        return IStream(OStream().putU32(self.c).putU32(self.t).data).getU64()
    def __str__(self):
        return str(int(self));
    def __cmp__(self, b):
        if int(self) < int(b):
            return -1
        elif int(self) > int(b):
            return 1
        else:
            return 0
    def __repr__(self):
        return str(self)

    def __eq__(self, b):
        return self.__cmp__(b) == 0
    def __ne__(self, b):
        return self.__cmp__(b) != 0
    def __le__(self, b):
        return self.__cmp__(b) < 0 or self.__cmp__(b) == 0
    def __lt__(self, b):
        return self.__cmp__(b) < 0
    def __ge__(self, b):
        return self.__cmp__(b) > 0 or self.__cmp__(b) == 0
    def __gt__(self, b):
        return self.__cmp__(b) > 0


class IStream(object):
    def __init__(self,data):
        self.data = data
        self.dlen = len(data)
        self.offset = 0

    def __str__(self):
        return str(self.data)

    def __unpack(self, fmt):
        r = struct.unpack_from(fmt, self.data, self.offset)
        self.offset += struct.calcsize(fmt)
        return r

    def getBlob(self, length):
        return self.__unpack('<{0}s'.format(length))[0]

    def getAll(self):
        return self.getBlob(self.inAvail())

    def getMsgId(self):
        id = self.getU64()
        return MsgId(id)

    def getRid(self):
        return Rid.fromU64(self.getU64())

    def getIproHdr(self):
        return (self.getU32(), self.getU32(), self.getU32())

    def getU8(self):
        return self.__unpack('B')[0];

    def getU16(self):
        return self.__unpack('<H')[0];

    def getU16n(self):
        return self.__unpack('>H')[0];

    def getU32(self):
        return self.__unpack('<L')[0];

    def getU64(self):
        return self.__unpack('<Q')[0];

    def getLps(self):
        length = self.getU32()
        return IStream(self.__unpack('<{0}s'.format(length))[0])

    def getStr(self):
        return str(self.getLps().data, encoding='utf8')

    def getTlv(self):
        return self.getU32(), self.getLps()

    def Tlvs(self):
        while self.inAvail():
            tag = self.getU32()
            val = self.getLps()
            yield (tag, val)

    def tlvForeach(self, cbmap):
        while self.inAvail():
            t,v = self.getTlv()
            if t in cbmap:
                cbmap[t](v)

    def Lpss(self):
        while self.inAvail():
            lps = self.getLps()
            yield lps

    def getVarInt(self):
        v = varint.decode_bytes(self.data[self.offset:])
        self.offset += len(varint.encode(v))
        return v

    def getVarIntLps(self):
        length = self.getVarInt()
        return IStream(self.__unpack('<{0}s'.format(length))[0])

    def getVarIntLpsNum(self):
        length = self.getVarInt()
        r = IStream(self.__unpack('<{0}s'.format(length))[0])
        if(length == 2):
            return r.getU16()
        if(length == 4):
            return r.getU32()
        if(length == 8):
            return r.getU64()

    def getIPv4(self):
        return [self.getU8(), self.getU8(), self.getU8(), self.getU8()]

    def getMishasFuckingInt(self):
        isize = self.getU8()
        if isize == 0:
            return 0
        elif isize == 1:
            return self.getU8()
        elif isize == 2:
            return self.getU16()
        elif isize == 3:
            return self.getU16() + self.getU8() * 65536
        elif isize == 4:
            return self.getU32()
        raise Exception('invalid MishasFuckingInt')

    def getTlvset(self):
        tlvset = {}
        while self.inAvail():
            t,v = self.getTlv()
            tlvset[t] = v
        return tlvset

    def inAvail(self):
        return self.dlen - self.offset

class OStream(object):
    def __init__(self, data = bytes()):
        self.data = data

    def __str__(self):
        return str(self.data)

    def __pack(self, fmt, *args):
        self.data += struct.pack(fmt, *args)
        return self

    def putU8(self, num):
        return self.__pack('B', num)

    def putMsgId(self, mid):
        return self.putU64(int(mid))

    def putU16(self, num):
        return self.__pack('<H', num)

    def putU16n(self, num):
        return self.__pack('>H', num)

    def putU32(self, num):
        return self.__pack('<L', num)

    def putI32(self, num):
        return self.__pack('<l', num)

    def putRid(self, type, id):
        return self.putU64(int(Rid(type, id)))

    def putChatId(self, id):
        return self.putRid(2, id)

    def putMchatHdr(self, type, id):
        return self.putReqId().putRid(type, id).putOrigin()

    def putU64(self, num):
        return self.__pack('<Q', num)

    def putLps(self, data):
        self.putU32(len(data))
        return self.putBlob(data)

    def putBlob(self, data):
        if isinstance(data, str):
            data = bytes(data, encoding='utf8')
        return self.__pack('<{0}s'.format(len(data)), data)

    def putTlv(self, tag, data):
        self.putU32(tag)
        return self.putLps(data)

    def putTlvU32(self, tag, n):
        self.putU32(tag)
        return self.putLps(OStream().putU32(n).data)

    def putIPkt(self, msg, data):
        self.putU32(msg)
        self.putU32(len(data))
        self.putU32(0)
        return self.putBlob(data)

    def putISPkt(self, msg, key, data):
        paylo = OStream().putLps(key).putBlob(data)

        self.putU16(msg)
        self.putU16(1)
        self.putU32(len(paylo.data))
        self.putU32(0)
        return self.putBlob(paylo.data)

    def putIPv4(self, addr):
        if isinstance(addr, list):
            assert(len(addr) == 4)
            addr = '.'.join([str(o) for o in addr])

        self.putBlob(socket.inet_aton(addr))

    def encloseLps(self):
        return OLps(self)

    def encloseCLps(self):
        return OCLps(self)

class OLps(OStream):
    def __init__(self, ostream):
        super(OLps, self).__init__()
        self.ostream = ostream

    def __enter__(self):
        return self

    def __exit__(self, exception, value, traceback):
        if exception:
            return False

        self.ostream.putLps(self.data)

class OCLps(OLps):
    def __init__(self, ostream):
        super(OCLps, self).__init__(ostream)
        self.lpsCount = 0

    def putLps(self, data):
        super(OCLps, self).putLps(data)
        self.lpsCount += 1

    def __exit__(self, exception, value, traceback):
        self.data = struct.pack('<L', self.lpsCount) + self.data
        super(OCLps, self).__exit__(exception, value, traceback)

class IPacket(IStream):
    def __init__(self, msg, seq, proto, data):
        super(IPacket, self).__init__(data)
        self.proto = proto
        self.msg = msg
        self.seq = seq

    @staticmethod
    def create(hdr, data):
        _, proto, seq, msg = struct.unpack_from('<L L 2L', hdr)
        return IPacket(msg, seq, proto, data)
