# Bluetooth temperature and humidity sensor to homebridge-http-webhooks
There are several bluetooth humidity and temperature monitoring devices
when used with a Raspberry Pi Zero W board make for an inexpensive
whole-home monitoring system.

## Installation
Place the `srv.py` and `default.cfg` in the same directory anywhere
you'd like. It can also be run directly from the Git repo. The user
running `srv.py` needs rights to open and use the bluetooth adapter.

The external [bleson library](https://pypi.org/project/bleson/) is used
for parsing Bluetooth advertisements and can be installed with
`pip install --user bleson`.

## Server setup
By default `srv.py` reads `default.cfg`. You can specify a different
config file with the `-c` argument. All the configuration parameters
are explained in comments inside of `default.cfg`.

## Bluetooth devices
Supported devices are the following:
- [Govee H5075](https://www.amazon.com/dp/B0872X4H4J) - good ambient room monitor and when purchased in a 2-pack are quite affordable.
- [Inkbird IBS-TH2](https://www.amazon.com/dp/B08S34C5X9) - smaller, magnetic, and water resistant make this a better option for monitoring refrigerators and freezers.

All you need to setup monitoring is the MAC address of the device. The
MAC can be found with the included `btscan.py` utility or the Linux
command `sudo hcitool lescan`.

## Homebridge setup
The homebridge-http-webhooks plugin with `HTTP` access and no
authorization is required. Currently only the Temperature and Humidity
sensor types are supported. A 1:1 map is necessary between each
temperature/humidity device and a webhooks accessory ID name.
