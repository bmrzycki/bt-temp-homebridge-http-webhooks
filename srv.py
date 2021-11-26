#!/usr/bin/env python3

import argparse
import syslog

from configparser import ConfigParser
from pathlib import Path
from json import loads
from signal import signal, SIGPIPE, SIG_DFL
from struct import unpack
from sys import argv
from threading import Lock
from time import sleep
from urllib.parse import quote
from urllib.request import urlopen

import bleson  # Developed using ver 0.1.8 from pip

BATTERY = {
    'id' : '',
    'threshold' : 50,
}
GLOBAL = {
    'url_timeout' : 5.0,
    'interval'    : 60,
}
VERBOSE = 0
WEBHOOKS = {
    'host'  : '127.0.0.1',
    'port'  : 51828,
    'delay' : 0.2,
}

_BT = {  # mac str -> BTData() class
}
_BT_LOCK = Lock()

class BTData():
    def __init__(self, model, mac):
        self.model = model
        self.mac = mac
        self.msg = ''
        self._data = {}
        self._webhook = {}
        self._mac_valid()
        self._model_valid()

    def __repr__(self):
        return (f"BTData(mac='{self.mac}' model='{self.model}'"
                f" webhook={self._webhook})")

    def reset(self):
        self._data = {}

    def data(self):
        if not self.ok() or not self._data:
            return {}
        return { 'name'     : self._data['ad'].name,
                 'rssi'     : self._data['ad'].rssi,
                 'mfg_data' : self._mfg_data(),
                 'c'        : self._data['c'],
                 'f'        : round((self._data['c'] * 1.80) + 32.0,
                                    self.ndigits()),
                 'h'        : self._data['h'],
                 'b'        : self._data['b'] }

    def webhook_add(self, kind, name):
        if kind and name:
            self._webhook[kind] = name

    def webhooks(self):
        return { 'c' : self._webhook.get('temperature', ''),
                 'h' : self._webhook.get('humidity', ''),
                 'b' : self._webhook.get('battery', '') }

    def ok(self):
        return not self.msg

    def ndigits(self):
        if self.model == 'gvh5075':
            return 1
        return 2

    def parse(self, ad):
        if self.ok() and ad.mfg_data and self.mac == ad.address.address:
            fn_name = f"_parse_{self.model}"
            parse = getattr(self, fn_name, None)
            if parse is None:
                raise RuntimeError("{fn_name} function not found")
            parse(ad)

    def _mfg_data(self):
        ad = self._data.get('ad', None)
        if ad is not None:
            x = ad.mfg_data.hex().lower()
            xlen = len(x)
            return ' '.join(x[i:i+2] for i in range(0, xlen, 2))
        return ''

    def _mac_valid(self):
        if ':' not in self.mac:
            self.msg = f"MAC '{self.mac}' not separated with ':'"
            return
        sp = self.mac.split(':')
        if len(sp) != 6:
            self.msg = f"MAC '{self.mac}' not length 6"
            return
        for el in sp:
            if len(el) != 2:
                self.msg = f"MAC '{self.mac}' el='{el}' invalid"
                return
            try:
                n = int(el, 16)
            except Exception as e:
                self.msg = f"MAC '{self.mac}' el='{el}' not hex: {str(e)}"
                return

    def _model_valid(self):
        return f"_parse_{self.model}" in dir(self)

    def _parse_gvh5075(self, ad):
        # The Govee H5075 advertises temperature and humidity inside its
        # own manufacture data byte string of length=8:
        #   88 ec 00 80 0b 38 64 00  <-- negative temperature
        #   88 ec 00 00 03 73 64 00  <-- positive temperature
        #
        # Bytes     Field
        #   0-1     Manufacturer key (88 ec)
        #     2     (unknown, seems to always be 00)
        #   3-5     encoded temperature and humidity
        #     6     battery remaning percentage
        #     7     (unknown, seems to always be 00)
        #
        # The temperature encoding in bytes:
        #   0-22    combined temperature and humidity data
        #     23    sign bit (0 = positive temp, 1 = negative temp)
        #
        # For whatever reason the encoding doesn't use 2s compliment: the
        # data is always converted as if it were unsigned. The encoding
        # is packed as decimal values where both the temperature and
        # humidity have a single significant digit. The temperature is
        # stored in Celsius regardless of the mode switch on the Govee.
        # Some examples with temperatures in column zero and humidity
        # percentage in column 1:
        #    23.4, 40.9  ->   234409, sign=0
        #     0.1, 33.0  ->     1330, sign=0
        #    -2.3, 88.9  ->    23889, sign=1
        #   148.2, 10.1  ->  1482101, sign=0
        #
        # The H5075 sends different advertisements and only ones with
        # Manufacturer ID UUID 16 (0xec88) have temperature data.
        if bleson.UUID16(0xec88) in ad.uuid16s:
            raw = int(ad.mfg_data[3:6].hex(), 16)
            data, sign = raw & 0x7fffff, raw & 0x800000
            h = (data % 1000)
            c = data - h
            if sign:
                c *= -1
            self._data = {
                'ad' : ad,
                'c'  : round(c / 10000.0, self.ndigits()),
                'h'  : round(h / 10.0, self.ndigits()),
                'b'  : ad.mfg_data[6] }

    def _parse_ibsth2(self, ad):
        # The manufacturer data for the Inkbird TH2 contains the following
        # in little-endian ordering:
        #   2 bytes signed short: floor(temperature_c * 100)
        #   2 bytes signed short: floor(humidity * 100)
        #   3 bytes: (unknown)
        #   1 byte: battery percentage
        #   1 byte: (unknown)
        c, h, _, _, _, b, _ = unpack("<2h5b", ad.mfg_data)
        self._data = {
            'ad' : ad,
            'c'  : round(c / 100.0, self.ndigits()),
            'h'  : round(h / 100.0, self.ndigits()),
            'b'  : b }


def error(msg):
    syslog.syslog(syslog.LOG_ERR, msg)


def info(msg):
    if VERBOSE > 1:
        syslog.syslog(syslog.LOG_INFO, msg)


def whook(args):
    url, query = f"http://{WEBHOOKS['host']}:{WEBHOOKS['port']}/", []
    for k in args:
        query.append(f"{quote(k, safe='')}={quote(str(args[k]), safe='')}")
    if query:
        url += '?' + '&'.join(query)
    try:
        rsp = urlopen(url=url, timeout=GLOBAL['url_timeout'])
    except Exception as e:
        error(f"HTTP request exception {e} for url='{url}'")
        return
    if rsp.status != 200:
        error(f"bad status={rsp.status} for url='{url}'")
        return
    info(f"updated url='{url}'")


def callback(ad):
    bt, d = _BT.get(ad.address.address, None), {}
    if bt is None:
        return
    try:
        _BT_LOCK.acquire()
        bt.parse(ad)
        d = bt.data()
    finally:
        _BT_LOCK.release()
    if VERBOSE > 0 and d:
        s = f"c={d['c']:.2f} f={d['f']:.2f} h={d['h']:.2f}% b={d['b']}%"
        if VERBOSE > 1:
            s += f" mfg_data='{d['mfg_data']}'"
            s += f" name='{d['name']}' rssi={d['rssi']}"
        print(f"{bt.mac}  {s}")


def update():
    def _u(hooks, data):
        for k in hooks:
            if hooks[k]:
                whook({'accessoryId' : hooks[k], 'value' : data[k]})
                sleep(WEBHOOKS['delay'])
    # Don't need _BT_LOCK: the observer is stopped so thread callbacks
    # can't happen during this function.
    batt = 100
    for mac in _BT:
        bt = _BT[mac]
        d = bt.data()
        if d:
            _u(bt.webhooks(), d)
            batt = min(batt, d.get('b', 100))
        bt.reset()
    if BATTERY['id'] and batt < BATTERY['threshold']:
        whook({'accessoryId' : BATTERY['id'], 'state' : 'true'})
        sleep(WEBHOOKS['delay'])


def observe(o):
    try:
        o.start()
        sleep(GLOBAL['interval'])
    finally:
        o.stop()
    update()


def main(args_raw):
    global VERBOSE
    p = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Bluetooth temperature sensor bridge to'
        ' homebridge-http-webhooks')
    p.add_argument(
        '-c', '--config',
        type=argparse.FileType('r', encoding='utf-8'),
        default=str(Path(__file__).parent.resolve().joinpath('default.cfg')),
        help='config file')
    p.add_argument(
        '-v', '--verbose',
        default=VERBOSE, action='count',
        help='verbosity, repeat to increase')
    args = p.parse_args(args_raw)
    VERBOSE = args.verbose
    cfg = ConfigParser()
    try:
        cfg.read_file(args.config)
    except Exception as e:
        p.error(str(e))

    GLOBAL['url_timeout'] = cfg.getfloat('global', 'url_timeout',
                                         fallback=GLOBAL['url_timeout'])
    GLOBAL['interval'] = cfg.getint('global', 'interval',
                                    fallback=GLOBAL['interval'])
    BATTERY['id'] = cfg.get('battery', 'id',
                            fallback=BATTERY['id'])
    BATTERY['threshold'] = cfg.getint('battery', 'threshold',
                                      fallback=BATTERY['threshold'])
    if not 1 <= BATTERY['threshold'] <= 100:
        p.error(f"Invalid battery threshold '{BATTERY['threshold']}'")
    WEBHOOKS['host'] = cfg.get('webhooks', 'host',
                               fallback=WEBHOOKS['host'])
    WEBHOOKS['port'] = cfg.getint('webhooks', 'port',
                                  fallback=WEBHOOKS['port'])
    WEBHOOKS['delay'] = cfg.getfloat('webhooks', 'delay',
                                     fallback=WEBHOOKS['delay'])
    for sect in cfg.sections():
        if sect.startswith('bt.'):
            mac = sect.partition('.')[2].upper()
            model = cfg.get(sect, 'model', fallback='gvh5075')
            bt = BTData(model, mac)
            if not bt.ok():
                p.error(bt.msg)
            for k in ('temperature', 'humidity', 'battery'):
                bt.webhook_add(k, cfg.get(sect, k, fallback=''))
            _BT[mac] = bt

    if args.verbose:
        for d, n in ((GLOBAL, 'global'), (WEBHOOKS, 'webhooks'), (_BT, 'bt')):
            for k in sorted(d):
                print(f"{n}.{k} = {d[k]}")

    syslog.openlog('bt-temp-whook', logoption=syslog.LOG_PID)
    bleson.logger.set_level(bleson.logger.ERROR)
    o = bleson.Observer(bleson.get_provider().get_adapter())
    o.on_advertising_data = callback
    while True:
        try:
            observe(o)
        except KeyboardInterrupt:
            break


if __name__ == '__main__':
    signal(SIGPIPE, SIG_DFL)  # Avoid exceptions for broken pipes
    main(argv[1:])
