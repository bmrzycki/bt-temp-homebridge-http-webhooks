#!/usr/bin/env python3

import bleson  # Developed using ver 0.1.8 from pip

from signal import signal, SIGPIPE, SIG_DFL
from threading import Lock
from time import sleep

_BT = set()
_LOCK = Lock()
_NAME_MAXLEN = 0

def callback(ad):
    global _NAME_MAXLEN
    if ad.mfg_data:
        mac = ad.address.address
        try:
            _LOCK.acquire()
            if (mac.startswith('A4:C1:38:') and
                bleson.UUID16(0xec88) in ad.uuid16s):
                _BT.add((mac, 'Govee H5075', ad.name))
                _NAME_MAXLEN = max(_NAME_MAXLEN, len(ad.name))
            elif mac.startswith('49:42:08:') and len(ad.mfg_data) == 9:
                _BT.add((mac, 'Inkbird IBS-TH2', ad.name))
                _NAME_MAXLEN = max(_NAME_MAXLEN, len(ad.name))
        finally:
            _LOCK.release()


def main():
    bleson.logger.set_level(bleson.logger.ERROR)
    o = bleson.Observer(bleson.get_provider().get_adapter())
    o.on_advertising_data = callback

    print('Observing Bluetooth advertisements for 10 seconds...')
    try:
        o.start()
        sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        o.stop()

    if _BT:
        print(f"Found {len(_BT)} potential devices:")
        for m, k, n in sorted(list(_BT)):
            n = n.ljust(_NAME_MAXLEN)
            print(f"  {m}  {n}  {k}")


if __name__ == '__main__':
    signal(SIGPIPE, SIG_DFL)  # Avoid exceptions for broken pipes
    main()
