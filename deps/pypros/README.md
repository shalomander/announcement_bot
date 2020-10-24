# pypros

Python implementation of ipros protocol

## Client usage example

```python
#!/bin/env python3.6
import pypros
from pypros.log import log
import asyncio
from pypros.packet import Request

pypros.ctlr.init(self_alias='pyprocl.a.pyprocl-1', host='127.0.0.1', port=2410)

loop = asyncio.get_event_loop()
try:
    while True:
        r1 = pypros.send('pypros', b'test_a', 1, b'')
        r2 = pypros.send('pypros', b'test_b', 1, b'')
        r3 = asyncio.sleep(1)
        r = loop.run_until_complete(asyncio.gather(r1,r2,r3))
        log.warn(r)
finally:
    loop.run_until_complete(pypros.ipros.shutdown())


loop.close()
```

## Server usage example

```python
#!/bin/env python3.6
import sys
import re
import asyncio

import pypros
from pypros.log import log
from pypros.ipros import IncomingRequest

async def process(rq: IncomingRequest):
    log.info('{}: process called'.format(rq))
    rq.reply(200, 'ok')

if len(sys.argv) < 3:
    log.error('Invalid usage: expected ./s.py <alias> <ip:port>')
    sys.exit(1)

alias = sys.argv[1]
host,port = re.compile('(.*):(.*)').match(sys.argv[2]).groups()
port = int(port)

pypros.ctlr.init(self_alias=alias, host='127.0.0.1', port=2410)

loop = asyncio.get_event_loop()
server = None
try:
    server = loop.run_until_complete(pypros.listen(host, port, process))
    loop.run_forever()
finally:
    if server:
        server.close()
    loop.run_until_complete(pypros.ipros.shutdown())

loop.close()
```
