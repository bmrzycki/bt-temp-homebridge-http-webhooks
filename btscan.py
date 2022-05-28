#!/usr/bin/env python3

import argparse
import bleson  # Developed using ver 0.1.8 from pip

from configparser import ConfigParser
from signal import signal, SIGPIPE, SIG_DFL
from sys import argv
from threading import Lock
from time import sleep

from srv import BTData  # local import

_BT = {}
_LOCK = Lock()
_MAXLEN_NAME = 0
_IGNORE = []
VERBOSE = 0

def _add(bd, ad):
    global _MAXLEN_NAME
    bd.parse(ad)
    d = bd.data()
    if not d:
        return
    _LOCK.acquire()
    try:
        el = _BT.get(bd.mac, { 'model' : bd.model,
                               'c'     : [],
                               'f'     : [],
                               'h'     : [],
                               'b'     : [],
                               'r'     : [] })
        el['name'] = ad.name  # save most recent name, may change
        for n in ('c', 'h', 'b', 'f'):
            el[n].append(d[n])
        el['r'].append(ad.rssi)
        _BT[bd.mac] = el
        _MAXLEN_NAME = max(_MAXLEN_NAME, len(ad.name))
    finally:
        _LOCK.release()


def callback(ad):
    if not ad.mfg_data:
        return
    mac = ad.address.address
    if mac in _IGNORE:
        return
    if mac.startswith('A4:C1:38:') and bleson.UUID16(0xec88) in ad.uuid16s:
        _add(BTData('gvh5075', mac), ad)
    elif mac.startswith('49:42:08:') and len(ad.mfg_data) == 9:
        _add(BTData('ibsth2', mac), ad)


def main(args_raw):
    global VERBOSE
    p = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Bluetooth supported device scanner')
    p.add_argument(
        '-t', '--time',
        type=int, default=10,
        help='observation time in seconds')
    p.add_argument(
        '-i', '--ignore',
        action='append', default=[],
        help='mac addresses to ignore')
    p.add_argument(
        '-I', '--ignore-config',
        type=argparse.FileType('r', encoding='utf-8'),
        default=None, help='ignore macs from config file')
    p.add_argument(
        '-v', '--verbose',
        default=VERBOSE, action='count',
        help='verbosity, repeat to increase')
    args = p.parse_args(args_raw)
    VERBOSE = args.verbose
    if args.time < 1:
        p.error("--time must be 1 second or longer")
    for mac in args.ignore:
        mac = mac.upper()
        if mac not in _IGNORE:
            _IGNORE.append(mac)

    if args.ignore_config:
        cfg = ConfigParser()
        try:
            cfg.read_file(args.ignore_config)
        except Exception as e:
            p.error(str(e))
        for sect in cfg.sections():
            if sect.startswith('bt.'):
                mac = sect.partition('.')[2].upper()
                if mac not in _IGNORE:
                    _IGNORE.append(mac)

    if VERBOSE > 1:
        print(f"# ignore list: {_IGNORE}")

    bleson.logger.set_level(bleson.logger.ERROR)
    o = bleson.Observer(bleson.get_provider().get_adapter())
    o.on_advertising_data = callback

    print(f"Observing Bluetooth advertisements for {args.time} seconds...")
    try:
        o.start()
        sleep(args.time)
    except KeyboardInterrupt:
        pass
    finally:
        o.stop()

    bt_len = len(_BT)
    if bt_len == 0:
        print("No devices found")
        return
    elif bt_len == 1:
        print(f"Found {bt_len} device:")
    else:
        print(f"Found {bt_len} devices:")
    names = { 'b' : '    Battery (%)',
              'c' : 'Temperature (C)',
              'f' : 'Temperature (F)',
              'h' : '   Humidity (%)',
              'r' : '     RSSI (dBm)' }
    for k in sorted(_BT):
        d = _BT[k]

        print(f"  mac={k}  model='{d['model']}'  name='{d['name']}'")
        for n in ('c', 'f', 'h', 'b', 'r'):
            tmp, tmp_len = sorted(d[n]), len(d[n])
            lo, hi, avg = tmp[0], tmp[-1], sum(tmp) / tmp_len
            print(f"    {names[n]} : lo={lo} hi={hi} avg={avg:.02f}"
                  f" count={tmp_len}")


if __name__ == '__main__':
    signal(SIGPIPE, SIG_DFL)  # Avoid exceptions for broken pipes
    main(argv[1:])
