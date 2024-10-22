#!/usr/bin/env python3
"Print battery levels from bluetooth log"

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from configparser import ConfigParser
from csv import reader as csv_reader
from pathlib import Path
from signal import SIG_DFL, SIGPIPE, signal
from sys import stdout


def main():
    """
    The main routine.
    """
    parser = ArgumentParser(
        formatter_class=ArgumentDefaultsHelpFormatter,
        description="get battery values from a config and log",
    )
    parser.add_argument("cfg", help="configuration file")
    parser.add_argument("log", help="log file")
    args = parser.parse_args()
    args.cfg = Path(args.cfg).resolve()
    if not args.cfg.is_file():
        parser.error(f"cfg file doesn't exist '{args.cfg}'")
    args.log = Path(args.log).resolve()
    if not args.log.is_file():
        parser.error(f"log file doesn't exist '{args.log}'")

    config = ConfigParser()
    config.read(args.cfg)
    # pylint: disable=consider-using-with
    infile = open(args.log, encoding="utf-8")
    cfile = csv_reader(infile)

    data = {}
    for section in config.sections():
        if not section.startswith("bt."):
            continue
        data[section[3:]] = {
            "name": config[section]["temperature"],
        }

    for row in cfile:
        if len(row) < 2 or row[0].startswith("#"):
            continue  # Ignore blank rows and the CSV header.
        # date, mac, model, name, c_temp, humid, battery, rssi = row
        try:
            data[row[1]]["date"] = row[0]
            data[row[1]]["battery"] = int(row[6])
        except:
            print(row)
            raise
    infile.close()
    show(data)


def show(data):
    """
    Using dict data show the output.
    """
    # Place in a list of tuples to sort the final values
    final = []
    for mac, elem in data.items():
        if "battery" in elem:
            final.append([elem["battery"], elem["date"], mac])
        else:
            print(f"warning: missing battery for {elem['name']}")
    for battery, date, mac in sorted(final):
        name = data[mac]["name"]
        if name.startswith("t_"):
            name = name[2:]
        stdout.write(
            f"{name}\n"
            + f"  battery  {battery} %\n"
            + f"     date  {date}\n"
            + f"      mac  {mac}\n"
        )


if __name__ == "__main__":
    signal(SIGPIPE, SIG_DFL)  # Avoid exceptions for broken pipes
    main()
