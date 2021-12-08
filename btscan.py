#!/usr/bin/env python3

import bleson  # Developed using ver 0.1.8 from pip

from signal import signal, SIGPIPE, SIG_DFL
from threading import Lock
from time import sleep

_BT = {}
_LOCK = Lock()
_MAXLEN_NAME = 0

def _add(mac, model, ad):
    global _MAXLEN_NAME
    _LOCK.acquire()
    try:
        d = _BT.get(mac, { 'model' : model,
                           'batt'  : ad.mfg_data[-2],
                           'rssi'  : [] })
        d['name'] = ad.name  # save most recent name, may change
        d['rssi'].append(ad.rssi)
        _BT[mac] = d
        _MAXLEN_NAME = max(_MAXLEN_NAME, len(ad.name))
    finally:
        _LOCK.release()


def callback(ad):
    if not ad.mfg_data:
        return
    mac = ad.address.address
    if mac.startswith('A4:C1:38:') and bleson.UUID16(0xec88) in ad.uuid16s:
        _add(mac, 'Govee H5075    ', ad)
    elif mac.startswith('49:42:08:') and len(ad.mfg_data) == 9:
        _add(mac, 'Inkbird IBS-TH2', ad)


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

    if not _BT:
        print("No supported devices found")
        return

    print(f"Found {len(_BT)} supported device(s):")
    for k in sorted(_BT):
        d = _BT[k]
        r, n = sorted(d['rssi']), d['name'].ljust(_MAXLEN_NAME)
        rm, rx, ra = r[0], r[-1], sum(r)/float(len(r))
        # mac  model  name  rssi_min  rssi_max rssi_avg  battery_%
        print(f"  {k}  {d['model']}  {n}  {rm}  {rx}  {ra:.2f}  {d['batt']}%")


if __name__ == '__main__':
    signal(SIGPIPE, SIG_DFL)  # Avoid exceptions for broken pipes
    main()
