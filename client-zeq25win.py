#!/usr/bin/env python3
"""
client-zeq25win.py  –  Client for the ZEQ25 server
Python 3.13

Sends LX200 iOptron commands to server-zeq25.py via TCP socket.
Coordinates are passed as command-line parameters.

Quick usage:
  python client-zeq25win.py --get-ra
  python client-zeq25win.py --get-dec
  python client-zeq25win.py --get-alt
  python client-zeq25win.py --get-azm
  python client-zeq25win.py --ra 23:22:20 --dec +45:30:00
  python client-zeq25win.py --cmd ":V#"
"""

import sys
import argparse
import socket
import configparser

import arrow


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(config_file='config.cfg'):
    config = configparser.ConfigParser()
    config.read(config_file)
    return config


# ---------------------------------------------------------------------------
# Communication with the server
# ---------------------------------------------------------------------------

def send_command(host: str, port: int, command: str, timeout: float = 5.0, token: str = '') -> str:
    """Sends an LX200 command to the server and returns the response."""
    payload = f"{token}|{command}" if token else command
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendall(payload.encode('utf-8'))
            try:
                reply = s.recv(1024).decode('utf-8', errors='replace')
            except socket.timeout:
                reply = ''
        return reply
    except ConnectionRefusedError:
        print(f"Error: could not connect to {host}:{port}")
        print("  Is server-zeq25.py running?")
        sys.exit(1)
    except Exception as ex:
        print(f"Connection error: {ex}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Coordinate converters → LX200 commands
# ---------------------------------------------------------------------------

def ra_to_lx200(ra_str: str) -> str:
    """
    Converts RA to LX200 command :Sr HH:MM:SS#
    Accepted formats:
      "HH:MM:SS"  /  "HH:MM:SS.ss"
      "HHhMMmSS.sss"  (e.g.: "09h04m22.27s")
    """
    import re
    ra_str = ra_str.strip()

    # formato HHhMMmSS[.ss]s
    m = re.fullmatch(r'(\d+)h(\d+)m([\d.]+)s?', ra_str, re.IGNORECASE)
    if m:
        hh, mm, ss = m.group(1), m.group(2), m.group(3)
    else:
        parts = ra_str.split(':')
        if len(parts) != 3:
            raise ValueError(
                f"Invalid RA format: '{ra_str}'  "
                f"(expected HH:MM:SS or HHhMMmSS.sss)"
            )
        hh, mm, ss = parts

    return f":Sr {int(hh):02d}:{int(mm):02d}:{float(ss):05.2f}#"


def dec_to_lx200(dec_str: str) -> str:
    """
    Converts DEC to LX200 command :Sd sDD*MM:SS#
    Accepted formats:
      "[+-]DD:MM:SS"  /  "[+-]DD*MM:SS"
      "[+-]DD°MM'SS.ss\""  (e.g.: "+34°58'46.12\"")
    """
    import re
    dec_str = dec_str.strip()

    sign = '+'
    if dec_str and dec_str[0] in ('+', '-'):
        sign = dec_str[0]
        dec_str = dec_str[1:]

    # formato DD°MM'SS[.ss]"
    m = re.fullmatch(r"(\d+)[°º](\d+)[']?([\d.]+)[\"]?", dec_str)
    if m:
        dd, mm, ss = m.group(1), m.group(2), m.group(3)
    else:
        dec_str = dec_str.replace('*', ':')
        parts = dec_str.split(':')
        if len(parts) != 3:
            raise ValueError(
                f"Invalid DEC format: '{sign}{dec_str}'  "
                f"(expected [+-]DD:MM:SS or [+-]DD°MM'SS.ss\")"
            )
        dd, mm, ss = parts

    return f":Sd {sign}{int(dd):02d}*{int(mm):02d}:{float(ss):05.2f}#"


def alt_to_lx200(alt_str: str) -> str:
    """
    Converts altitude to LX200 command :Sa sDD*MM:SS#
    Accepted input: "[+-]DD:MM:SS" or "[+-]DD*MM:SS"
    """
    alt_str = alt_str.strip()
    sign = '+'
    if alt_str and alt_str[0] in ('+', '-'):
        sign = alt_str[0]
        alt_str = alt_str[1:]
    alt_str = alt_str.replace('*', ':')
    parts = alt_str.split(':')
    if len(parts) != 3:
        raise ValueError(f"Invalid ALT format: '{sign}{alt_str}'")
    dd, mm, ss = parts
    return f":Sa {sign}{int(dd):02d}*{int(mm):02d}:{float(ss):05.2f}#"


def azm_to_lx200(azm_str: str) -> str:
    """
    Converts azimuth to LX200 command :Sz DDD*MM:SS#
    Accepted input: "DDD:MM:SS" or "DDD*MM:SS"
    """
    azm_str = azm_str.strip().replace('*', ':')
    parts = azm_str.split(':')
    if len(parts) != 3:
        raise ValueError(f"Invalid AZM format: '{azm_str}'")
    dd, mm, ss = parts
    return f":Sz {int(dd):03d}*{int(mm):02d}:{float(ss):05.2f}#"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    config = load_config('config.cfg')
    default_host = config.get('server', 'host', fallback='127.0.0.1')
    if default_host == '0.0.0.0':
        default_host = '127.0.0.1'
    default_port = int(config.get('server', 'port', fallback='4000'))
    token = config.get('server', 'token_server', fallback='').strip()

    parser = argparse.ArgumentParser(
        description='ZEQ25 Client – sends commands to the iOptron ZEQ25 mount server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Get current position:
    python client-zeq25win.py --get-ra
    python client-zeq25win.py --get-dec
    python client-zeq25win.py --get-alt
    python client-zeq25win.py --get-azm

  Set coordinates and GOTO (automatic when passing --ra and --dec together):
    python client-zeq25win.py --ra 23:22:20 --dec +45:30:00
    python client-zeq25win.py --ra 09h04m22.27s --dec "+34°58'46.12\""

  Set RA only (without moving):
    python client-zeq25win.py --ra 06:45:08

  Set DEC only (without moving):
    python client-zeq25win.py --dec -16:42:58

  Set altitude and azimuth:
    python client-zeq25win.py --alt +45:00:00 --azm 180:00:00

  Firmware information:
    python client-zeq25win.py --get-version
    python client-zeq25win.py --get-info

  Direct LX200 command:
    python client-zeq25win.py --cmd ":MH#"

  Other server:
    python client-zeq25win.py --host 192.168.1.10 --port 4000 --get-ra
"""
    )

    # --- Connection ---
    parser.add_argument(
        '--host', default=default_host,
        help=f'Server host  (default: {default_host})'
    )
    parser.add_argument(
        '--port', type=int, default=default_port,
        help=f'Server port  (default: {default_port})'
    )

    # --- Coordinates: set ---
    coord_group = parser.add_argument_group('Coordinates (set on the mount)')
    coord_group.add_argument(
        '--ra', metavar='HH:MM:SS',
        help='Set Right Ascension'
    )
    coord_group.add_argument(
        '--dec', metavar='[+-]DD:MM:SS',
        help='Set Declination'
    )
    coord_group.add_argument(
        '--alt', metavar='[+-]DD:MM:SS',
        help='Set Altitude'
    )
    coord_group.add_argument(
        '--azm', metavar='DDD:MM:SS',
        help='Set Azimuth'
    )

    # --- Queries ---
    query_group = parser.add_argument_group('Queries')
    query_group.add_argument('--get-ra',      action='store_true', help='Get current RA')
    query_group.add_argument('--get-dec',     action='store_true', help='Get current DEC')
    query_group.add_argument('--get-alt',     action='store_true', help='Get current Altitude')
    query_group.add_argument('--get-azm',     action='store_true', help='Get current Azimuth')
    query_group.add_argument('--get-version', action='store_true', help='Firmware version')
    query_group.add_argument('--get-info',    action='store_true', help='Mount information')
    query_group.add_argument('--get-time',    action='store_true', help='Server time')
    query_group.add_argument('--get-date',    action='store_true', help='Server date')

    # --- Control ---
    ctrl_group = parser.add_argument_group('Control')
    ctrl_group.add_argument(
        '--go-home', action='store_true',
        help='Move to HOME position'
    )
    ctrl_group.add_argument(
        '--vel', type=int, metavar='1-9',
        help='N/S/E/W button speed (1–9)'
    )
    ctrl_group.add_argument(
        '--track-on',  action='store_true', help='Enable tracking'
    )
    ctrl_group.add_argument(
        '--track-off', action='store_true', help='Disable tracking'
    )
    ctrl_group.add_argument(
        '--cmd', metavar=':CMD#',
        help='Send direct LX200 command  (e.g.: ":V#")'
    )

    # --- Options ---
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show details of the commands sent'
    )

    args = parser.parse_args()

    host = args.host
    port = args.port
    verbose = args.verbose
    now = arrow.now()

    if verbose:
        print(f"[{now.format('HH:mm:ss')}] Connecting to {host}:{port}")

    actions_performed = False

    def do_cmd(command: str, label: str = '') -> str:
        nonlocal actions_performed
        if verbose:
            print(f"  >> Sending  : {command!r}")
        response = send_command(host, port, command, token=token)
        if label:
            resp_str = response if response else '(no response)'
            print(f"{label}: {resp_str}")
        elif verbose:
            print(f"  << Response : {response!r}")
        else:
            if response:
                print(response)
        actions_performed = True
        return response

    # ----------------------------------------------------------------
    # Queries
    # ----------------------------------------------------------------
    if args.get_ra:
        do_cmd(":GR#", "RA")
    if args.get_dec:
        do_cmd(":GD#", "DEC")
    if args.get_alt:
        do_cmd(":GA#", "Altitude")
    if args.get_azm:
        do_cmd(":GZ#", "Azimuth")
    if args.get_version:
        do_cmd(":V#", "Version")
    if args.get_info:
        do_cmd(":MountInfo#", "MountInfo")
    if args.get_time:
        do_cmd(":GL#", "Server time")
    if args.get_date:
        do_cmd(":GC#", "Server date")

    # ----------------------------------------------------------------
    # Control
    # ----------------------------------------------------------------
    if args.go_home:
        resp = do_cmd(":MH#", "GoHome")

    if args.vel is not None:
        if 1 <= args.vel <= 9:
            do_cmd(f":SR{args.vel}#", f"Speed {args.vel}")
        else:
            print("Error: --vel must be a number between 1 and 9")
            sys.exit(1)

    if args.track_on:
        do_cmd(":ST1#", "Tracking ON")
    if args.track_off:
        do_cmd(":ST0#", "Tracking OFF")

    if args.cmd:
        do_cmd(args.cmd)

    # ----------------------------------------------------------------
    # Fijar coordenadas y GOTO
    # ----------------------------------------------------------------
    if args.ra:
        try:
            cmd = ra_to_lx200(args.ra)
            resp = do_cmd(cmd, f"Set RA  {args.ra}")
            if resp and resp.strip() != '1':
                print(f"  Warning: unexpected response for Set RA: '{resp}'")
        except ValueError as ex:
            print(f"Error: {ex}")
            sys.exit(1)

    if args.dec:
        try:
            cmd = dec_to_lx200(args.dec)
            resp = do_cmd(cmd, f"Set DEC {args.dec}")
            if resp and resp.strip() != '1':
                print(f"  Warning: unexpected response for Set DEC: '{resp}'")
        except ValueError as ex:
            print(f"Error: {ex}")
            sys.exit(1)

    if args.alt:
        try:
            cmd = alt_to_lx200(args.alt)
            resp = do_cmd(cmd, f"Set ALT {args.alt}")
        except ValueError as ex:
            print(f"Error: {ex}")
            sys.exit(1)

    if args.azm:
        try:
            cmd = azm_to_lx200(args.azm)
            resp = do_cmd(cmd, f"Set AZM {args.azm}")
        except ValueError as ex:
            print(f"Error: {ex}")
            sys.exit(1)

    if args.ra and args.dec:
        resp = do_cmd(":MS#", "GOTO")
        if resp == '0':
            print("  → Slew started")
        elif resp == '1':
            print("  → Rejected: object below the horizon")
        else:
            print(f"  → GOTO response: {resp!r}")

    # ----------------------------------------------------------------
    # No arguments: show help and status
    # ----------------------------------------------------------------
    if not actions_performed:
        parser.print_help()
        print(f"\nConfigured server    : {host}:{port}")
        print(f"Local time           : {now.format('YYYY-MM-DD HH:mm:ss ZZ')}")


if __name__ == '__main__':
    main()
