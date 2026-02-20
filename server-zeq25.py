#!/usr/bin/env python3
"""
server-zeq25.py  –  Emulator/proxy server for iOptron ZEQ25 mount
Python 3.13 | Uses arrow for dates | Reads configuration from config.cfg

Listens on the configured port for LX200 iOptron protocol commands,
processes them in EmulZeq and validates/forwards to ASCOM if enabled.
"""

import sys
import re
import socket
import logging
import argparse
import configparser
from threading import Thread

import arrow

# ASCOM only available on Windows with ASCOM Platform installed
try:
    import win32com.client
    ASCOM_AVAILABLE = True
    print("win32com available: ASCOM enabled")
except ImportError:
    ASCOM_AVAILABLE = False
    print("win32com not available: ASCOM disabled")

# msvcrt only available on Windows
try:
    import msvcrt
    MSVCRT_AVAILABLE = True
    print("msvcrt available: console functions enabled")
except ImportError:
    MSVCRT_AVAILABLE = False
    print("msvcrt not available: console functions disabled")

from zeq25 import Zeq25

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_file='config.cfg'):
    config = configparser.ConfigParser()
    config.read(config_file)
    return config


# ---------------------------------------------------------------------------
# EmulZeq – ZEQ25 mount emulator with optional ASCOM support
# ---------------------------------------------------------------------------

class EmulZeq:
    def __init__(self, testing=True):
        self.zeq25data = Zeq25('/dev/null', testing)
        self._buffer = ''
        self.startingCommand = False
        self.endCommand = True
        self.waitingCommand = False
        self.AscomDeviceName = ''
        self.AscomDevice = None
        self.AscomConnected = False
        self.lastRA = []
        self.lastDec = []

    def initAscomDevice(self, sName):
        if not ASCOM_AVAILABLE:
            logger.warning("ASCOM not available on this platform (requires Windows)")
            return
        self.AscomDeviceName = sName
        self.AscomDevice = win32com.client.Dispatch(sName)
        todo_ok = False
        try:
            self.AscomDevice.Connected = True
            todo_ok = True
        except Exception as ex:
            logger.error(f"Error connecting ASCOM: {ex}")

        if todo_ok:
            self.AscomConnected = True
            self.AscomDevice.Tracking = True
            logger.info(f"Connection to {sName} – OK")
        else:
            logger.error(f"ERROR connection to {sName}")

    def goHome(self):
        self.zeq25data.goHome()
        if self.AscomConnected:
            self.AscomDevice.CommandString(":MH#")

    def MoveToRADec(self, aRA, aDec):
        """GoTo coordinates. aRA=[hh,mm,ss], aDec=[dd,mm,ss]."""
        self.lastRA = aRA
        self.lastDec = aDec
        self.zeq25data.setRA(aRA[0], aRA[1], aRA[2])
        self.zeq25data.setDec(aDec[0], aDec[1], aDec[2])
        self.zeq25data.move()
        if self.AscomConnected:
            ra_num = aRA[0] + aRA[1] / 60.0 + aRA[2] / 3600.0
            dec_num = aDec[0] + aDec[1] / 60.0 + aDec[2] / 3600.0
            try:
                self.AscomDevice.SlewToCoordinatesAsync(ra_num, dec_num)
                logger.info(f"ASCOM SlewToCoordinatesAsync RA={ra_num:.4f} DEC={dec_num:.4f}")
            except Exception as ex:
                logger.error(f"Error ASCOM SlewToCoordinates: {ex}")

    def setVelButton(self, vel):
        command = f":SR{vel}#"
        if self.AscomConnected:
            self.AscomDevice.CommandString(command)

    def processComand(self, command, debug=False):
        """
        Processes a complete LX200 iOptron command (":CMD#") and
        returns the response as a string.
        """
        ret = ''
        command = command.strip()
        if not command:
            return ret

        if command[-1] != '#' or command[0] != ':':
            return ret

        cmd = command[1:-1]   # strip ':' and '#'

        if cmd == 'V':
            ret = self.zeq25data.getVersion()

        elif cmd[:2] == 'FW':
            if len(cmd) > 2 and cmd[2] == '1':
                logger.debug("get fw1")
                ret = self.zeq25data.getFirmwareVersion()
            elif len(cmd) > 2 and cmd[2] == '2':
                logger.debug("get fw2")
                ret = self.zeq25data.getFirmwareMotorVersion()

        elif cmd == 'MountInfo':
            ret = self.zeq25data.getMountInfo()

        elif cmd[:2] == 'SR':        # SR – N/S/E/W button speed
            ret = '1'

        elif cmd[:2] == 'GD':        # GD – get Declination
            ret = self.zeq25data.getDec()

        elif cmd[:2] == 'GR':        # GR – get Right Ascension
            ret = self.zeq25data.getRA()

        elif cmd[:2] == 'GA':        # GA – get Altitude
            ret = self.zeq25data.getAltitude()

        elif cmd[:2] == 'GZ':        # GZ – get Azimuth
            ret = self.zeq25data.getAzimuth()

        elif cmd[:2] == 'GC':        # GC – get current Date (arrow)
            ret = arrow.now().format('MM/DD/YY') + '#'

        elif cmd[:2] == 'GL':        # GL – get local Time (arrow)
            ret = arrow.now().format('HH:mm:ss') + '#'

        elif cmd[:2] == 'GS':        # GS – get Sidereal Time (arrow UTC)
            ret = arrow.utcnow().format('HH:mm:ss') + '#'

        elif cmd[:2] == 'GG':        # GG – get GMT offset (arrow)
            offset = arrow.now().utcoffset()
            total_minutes = int(offset.total_seconds() // 60)
            sign = '+' if total_minutes >= 0 else '-'
            hh = abs(total_minutes) // 60
            mm = abs(total_minutes) % 60
            ret = f"{sign}{hh:02d}:{mm:02d}#"

        elif cmd[:2] == 'Sd':        # Sd – set Declination  sDD*MM:SS
            ret = '0'
            try:
                m = re.search(r'([\+\-]?\d+)\*(\d+):(\d+\.?\d*)', cmd)
                if not m:
                    raise ValueError("Invalid DEC format")
                nums = self.zeq25data._arrayStringToNum(list(m.groups()))
                self.lastDec = nums
                if self.zeq25data.setDec(nums[0], nums[1], nums[2]):
                    ret = '1'
            except Exception as ex:
                logger.error(f"Error Sd (set DEC): {ex}")
                ret = '0'

        elif cmd[:2] == 'Sr':        # Sr – set Right Ascension  HH:MM:SS
            ret = '0'
            try:
                m = re.search(r'(\d+):(\d+):(\d+\.?\d*)', cmd)
                if not m:
                    raise ValueError("Invalid RA format")
                nums = self.zeq25data._arrayStringToNum(list(m.groups()))
                self.lastRA = nums
                if self.zeq25data.setRA(nums[0], nums[1], nums[2]):
                    ret = '1'
            except Exception as ex:
                logger.error(f"Error Sr (set RA): {ex}")
                ret = '0'

        elif cmd[:2] == 'MS':        # MS – GOTO a RA/DEC fijados
            ret = '0'
            if self.zeq25data.move():
                ret = '0'  # '0' = slew possible, '1' = below horizon
                if self.AscomConnected and self.lastRA and self.lastDec:
                    ra_num = (self.lastRA[0]
                              + self.lastRA[1] / 60.0
                              + self.lastRA[2] / 3600.0)
                    dec_num = (self.lastDec[0]
                               + self.lastDec[1] / 60.0
                               + self.lastDec[2] / 3600.0)
                    try:
                        self.AscomDevice.SlewToCoordinatesAsync(ra_num, dec_num)
                        logger.info(
                            f"ASCOM SlewToCoordinatesAsync RA={ra_num:.4f} "
                            f"DEC={dec_num:.4f}"
                        )
                    except Exception as ex:
                        logger.error(f"Error ASCOM SlewToCoordinates: {ex}")

        elif cmd[:2] == 'MH':        # MH – goHome
            self.goHome()
            ret = '1'

        elif cmd[:2] == 'ST':        # ST0/ST1 – stop/start tracking
            if len(cmd) > 2 and cmd[2] == '1':
                ret = self.zeq25data.startTracking()
            else:
                ret = self.zeq25data.stopTracking()

        elif cmd[:2] == 'SE':        # SE? – is slewing?
            ret = '1' if self.zeq25data.isSlewing() else '0'

        return ret

    def on_data(self, data):
        if not self.waitingCommand:
            if data[0] == ':':
                self.waitingCommand = True
                self._buffer += data[0]
        else:
            if data[0] == '#':
                self.waitingCommand = False
                self._buffer += data[0]
                self.processComand(self._buffer)
                self._buffer = ''
            else:
                self._buffer += data[0]


# ---------------------------------------------------------------------------
# ObservationList – Observation list with arrow timestamp
# ---------------------------------------------------------------------------

class ObservationList:
    def __init__(self):
        self.listCoords = []
        self.nameFile = ''

    def setNameFile(self, name):
        if name:
            self.nameFile = name

    def saveFile(self):
        if self.nameFile:
            timestamp = arrow.now().format('YYYY-MM-DD_HH-mm-ss')
            fname = f"{self.nameFile}_{timestamp}.csv"
            with open(fname, 'w') as f:
                for item in self.listCoords:
                    f.write(f"{item[0]},{item[1]},,\n")
            self.reset()
            logger.info(f"Lista guardada en {fname}")

    def clearList(self):
        self.listCoords = []

    def add(self, ra, dec):
        ra = ra.rstrip('#')
        dec = dec.rstrip('#')
        self.listCoords.append((ra, dec))

    def delete(self, idx):
        self.listCoords.pop(idx)

    def pop(self):
        self.listCoords.pop()

    def reset(self):
        self.listCoords = []
        self.nameFile = ''

    def show(self):
        if not self.listCoords:
            print("  (empty list)")
        for i, item in enumerate(self.listCoords):
            print(f"  [{i}]  RA={item[0]}   Dec={item[1]}")


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

def print_help(ascom_enabled):
    print(
        "\n-------------------\n"
        "h: this menu\n"
        "f: file name\n"
        "s: save list (CSV)\n"
        "l: list RA/Dec\n"
        "a: add current RA/Dec\n"
        "d: delete list entry\n"
        "c: clear list\n"
       f"z: ASCOM connection: {ascom_enabled}\n"
        "v: N/S/E/W button speed (1-9)\n"
        "g: go to RA/Dec (GoTo)\n"
        "j: goHome\n"
        "t: current date/time (arrow)\n"
        "q: quit\n"
        "-------------------"
    )


def get_char():
    """Reads a single character from keyboard (cross-platform)."""
    if MSVCRT_AVAILABLE:
        ch = msvcrt.getch()
        return ch.decode('utf-8', errors='replace')
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch


def menu(char, zeq_emu, lista, ascom_enabled):
    if not char:
        return ascom_enabled
    print()
    if char == 'h':
        print_help(ascom_enabled)
    elif char == 's':
        lista.saveFile()
    elif char == 'l':
        lista.show()
    elif char == 'f':
        name = input('File name> ')
        lista.setNameFile(name)
    elif char == 'c':
        print("List cleared")
        lista.clearList()
    elif char == 'd':
        lista.show()
        try:
            i = int(input("list id to delete> "))
            lista.delete(i)
        except Exception as ex:
            print(f"Error: {ex}")
    elif char == 'a':
        ra = zeq_emu.zeq25data.getRA()
        dec = zeq_emu.zeq25data.getDec()
        lista.add(ra, dec)
        print(f"Added  RA={ra}  Dec={dec}")
    elif char == 'z':
        ascom_enabled = not ascom_enabled
        print(f"ASCOM connection = {ascom_enabled}")
        if ascom_enabled and not zeq_emu.AscomConnected:
            if not ASCOM_AVAILABLE:
                print("ASCOM not available (requires Windows with ASCOM Platform).")
            else:
                print("Opening ASCOM device chooser...")
                try:
                    chooser = win32com.client.Dispatch("ASCOM.Utilities.Chooser")
                    chooser.DeviceType = 'Telescope'
                    selected = chooser.Choose(None)
                except Exception as ex:
                    logger.error(f"Error ASCOM Chooser: {ex}")
                    print(f"Error opening ASCOM chooser: {ex}")
                    selected = None
                if selected:
                    zeq_emu.initAscomDevice(selected)
                else:
                    print("No ASCOM device selected.")
    elif char == 'g':
        try:
            ra_str = input("RA  (HH:MM:SS.ss)> ")
            dec_str = input("Dec (+/-DD:MM:SS.ss)> ")
            ra_parts = ra_str.strip().split(':')
            dec_parts = dec_str.strip().lstrip('+').split(':')
            aRA = [int(ra_parts[0]), int(ra_parts[1]), float(ra_parts[2])]
            aDec = [int(dec_parts[0]), int(dec_parts[1]), float(dec_parts[2])]
            print(f"  RA  = {aRA[0]:02d}:{aRA[1]:02d}:{aRA[2]:05.2f}")
            print(f"  Dec = {aDec[0]:+03d}:{aDec[1]:02d}:{aDec[2]:05.2f}")
            conf = input("Confirm GoTo? (Y to continue)> ").strip().upper()
            if conf == 'Y':
                zeq_emu.MoveToRADec(aRA, aDec)
                print("GoTo started.")
            else:
                print("GoTo aborted.")
        except Exception as ex:
            print(f"Coordinate error: {ex}")
    elif char == 'j':
        print("Go Home")
        zeq_emu.goHome()
    elif char == 'v':
        try:
            ivel = int(input("Speed (1..9): "))
            zeq_emu.setVelButton(ivel)
        except Exception:
            print("Numbers only, 1..9")
    elif char == 't':
        now = arrow.now()
        print(f"Local date/time  : {now.format('YYYY-MM-DD HH:mm:ss ZZ')}")
        print(f"UTC              : {arrow.utcnow().format('YYYY-MM-DD HH:mm:ss')} UTC")
    return ascom_enabled


# ---------------------------------------------------------------------------
# Servidor de sockets
# ---------------------------------------------------------------------------

def socket_server(config, use_ascom=True):
    port = int(config.get('server', 'port', fallback='4000'))
    host = config.get('server', 'host', fallback='0.0.0.0')
    token = config.get('server', 'token_server', fallback='').strip()
    ascom_enabled = use_ascom
    ascom_device = config.get('ascom', 'device', fallback='')

    zeq25 = EmulZeq(testing=True)
    lista = ObservationList()

    # Initialize ASCOM if enabled and available
    if ascom_enabled and ASCOM_AVAILABLE:
        if not ascom_device:
            print("Opening ASCOM device chooser...")
            try:
                chooser = win32com.client.Dispatch("ASCOM.Utilities.Chooser")
                chooser.DeviceType = 'Telescope'
                ascom_device = chooser.Choose(None)
            except Exception as ex:
                logger.error(f"Error ASCOM Chooser: {ex}")
                print(f"Error opening ASCOM chooser: {ex}")
        if ascom_device:
            zeq25.initAscomDevice(ascom_device)
        else:
            print("No ASCOM device selected.")
    elif ascom_enabled and not ASCOM_AVAILABLE:
        logger.warning("ASCOM enabled in config but win32com is not available")
        print("ASCOM requested but win32com is not available (requires Windows with ASCOM Platform).")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    logger.info("Socket created")

    try:
        srv.bind((host, port))
    except socket.error as msg:
        logger.error(f"Bind failed at {host}:{port} – {msg}")
        sys.exit(1)

    logger.info(f"Socket bound at {host}:{port}")
    srv.listen(10)
    logger.info(f"Listening on port {port}...")

    def client_thread(conn, addr):
        logger.info(f"Client connected: {addr[0]}:{addr[1]}")
        current_ra = zeq25.zeq25data.getRA()
        current_dec = zeq25.zeq25data.getDec()
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                command = data.decode('utf-8', errors='replace').strip()

                # Token authentication
                if token:
                    if '|' not in command:
                        logger.warning(f"[{addr[0]}] Missing token – command rejected")
                        conn.close()
                        return
                    recv_token, command = command.split('|', 1)
                    if recv_token != token:
                        logger.warning(f"[{addr[0]}] Invalid token – connection closed")
                        conn.close()
                        return

                reply = zeq25.processComand(command)
                if reply:
                    conn.sendall(reply.encode('utf-8'))
                new_ra = zeq25.zeq25data.getRA()
                new_dec = zeq25.zeq25data.getDec()
                if new_ra != current_ra or new_dec != current_dec:
                    current_ra = new_ra
                    current_dec = new_dec
                    ts = arrow.now().format('HH:mm:ss')
                    logger.info(
                        f"[{ts}] Position updated  "
                        f"RA={current_ra}  Dec={current_dec}"
                    )
        except Exception as ex:
            logger.error(f"Client error {addr[0]}: {ex}")
        finally:
            conn.close()
            logger.info(f"Client disconnected: {addr[0]}:{addr[1]}")

    def conn_thread():
        while True:
            try:
                conn, addr = srv.accept()
                t = Thread(target=client_thread, args=(conn, addr), daemon=True)
                t.start()
            except OSError:
                break
            except Exception as ex:
                logger.error(f"Error accept: {ex}")
                break

    Thread(target=conn_thread, daemon=True).start()

    now_str = arrow.now().format('YYYY-MM-DD HH:mm:ss ZZ')
    print(f"\n=== ZEQ25 Server started – {now_str} ===")
    print(f"    Port   : {port}  |  ASCOM : {'enabled' if ascom_enabled else 'disabled'}  |  Auth : {'enabled' if token else 'disabled'}\n")
    print_help(ascom_enabled)

    while True:
        try:
            ch = get_char()
            if ch in ('\x03', 'q'):   # Ctrl+C o 'q'
                print("\nExiting...")
                srv.close()
                sys.exit(0)
            else:
                ascom_enabled = menu(ch, zeq25, lista, ascom_enabled)
        except (KeyboardInterrupt, SystemExit):
            print("\nSaliendo...")
            srv.close()
            sys.exit(0)


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='ZEQ25 emulator/proxy server')
    parser.add_argument(
        '--no-ascom',
        dest='ascom',
        action='store_false',
        help='Disable ASCOM connection (enabled by default)'
    )
    parser.set_defaults(ascom=True)
    args = parser.parse_args()

    config = load_config('config.cfg')
    socket_server(config, use_ascom=args.ascom)


if __name__ == '__main__':
    main()
