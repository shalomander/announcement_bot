import re
from pypros.log import log
from pypros.IO import OStream,IStream
alias_re = re.compile('(.*)\.(.*)\.(.*)')

class Alias:
    def __init__(self, s: str):
        m = alias_re.match(s)
        if m is None:
            raise Exception('invalid alias: {}'.format(s))
        self.svc, self.host, self.conf = m.groups()

    def __repr__(self):
        return '{}.{}.{}'.format(self.svc, self.host, self.conf)

    def __str__(self):
        return repr(self)

    @classmethod
    def load(cls, istr: IStream):
        return cls('{}.{}.{}'.format(istr.getStr(), istr.getStr(), istr.getStr()))

    def dump(self) -> bytes:
        out = OStream()
        out.putLps(self.svc)
        out.putLps(self.host)
        out.putLps(self.conf)
        return out.data
