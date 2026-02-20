"""
tests/testServer.py
Tests for server-zeq25.py – EmulZeq, ObservationList and TCP server.
Python 3 / unittest
"""

import sys
import os
import socket
import threading
import time
import unittest
import importlib.util

import arrow

# ---------------------------------------------------------------------------
# Import server-zeq25 (name with hyphen → use importlib)
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
_SERVER_PATH = os.path.join(_BASE_DIR, 'server-zeq25.py')

spec = importlib.util.spec_from_file_location("server_zeq25", _SERVER_PATH)
server_zeq25 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_zeq25)

EmulZeq = server_zeq25.EmulZeq
ObservationList = server_zeq25.ObservationList


# ===========================================================================
# Tests de EmulZeq.processComand  (sin socket, sin ASCOM)
# ===========================================================================

class TestEmulZeqCommands(unittest.TestCase):
    """Tests all LX200 commands processed by EmulZeq."""

    def setUp(self):
        self.emu = EmulZeq(testing=True)

    # --- Basic format ---

    def test_empty_command_returns_empty(self):
        self.assertEqual(self.emu.processComand(''), '')

    def test_command_without_colon_returns_empty(self):
        self.assertEqual(self.emu.processComand('V#'), '')

    def test_command_without_hash_returns_empty(self):
        self.assertEqual(self.emu.processComand(':V'), '')

    # --- Information ---

    def test_getVersion(self):
        resp = self.emu.processComand(':V#')
        self.assertTrue(resp.startswith('V'), f"Expected 'V...' but got '{resp}'")

    def test_getFirmwareVersion_fw1(self):
        resp = self.emu.processComand(':FW1#')
        self.assertTrue(len(resp) > 0)

    def test_getFirmwareVersion_fw2(self):
        resp = self.emu.processComand(':FW2#')
        self.assertTrue(len(resp) > 0)

    def test_getMountInfo(self):
        resp = self.emu.processComand(':MountInfo#')
        self.assertIn(resp, ('8407', '8408', '8497', '8498'),
                      f"Unexpected MountInfo: '{resp}'")

    # --- Position query ---

    def test_getRA_returns_HH_MM_SS_format(self):
        resp = self.emu.processComand(':GR#')
        # Should be "HH:MM:SS#"
        self.assertTrue(resp.endswith('#'), f"Does not end with '#': '{resp}'")
        parts = resp.rstrip('#').split(':')
        self.assertEqual(len(parts), 3, f"Malformed RA: '{resp}'")

    def test_getDec_returns_DD_MM_SS_format(self):
        resp = self.emu.processComand(':GD#')
        self.assertTrue(resp.endswith('#'), f"Does not end with '#': '{resp}'")
        # Should contain '*'
        self.assertIn('*', resp, f"Malformed DEC: '{resp}'")

    def test_button_speed_SR(self):
        resp = self.emu.processComand(':SR5#')
        self.assertEqual(resp, '1')

    # --- Set RA ---

    def test_setRA_valid(self):
        resp = self.emu.processComand(':Sr 06:45:08.00#')
        self.assertEqual(resp, '1', f"Set RA should return '1', got '{resp}'")

    def test_setRA_updates_nextRA(self):
        self.emu.processComand(':Sr 06:45:08.00#')
        self.assertIsNotNone(self.emu.lastRA)
        self.assertEqual(len(self.emu.lastRA), 3)
        self.assertEqual(self.emu.lastRA[0], 6)
        self.assertEqual(self.emu.lastRA[1], 45)

    def test_setRA_invalid_format(self):
        resp = self.emu.processComand(':Sr NOVALIDO#')
        self.assertEqual(resp, '0')

    # --- Set DEC ---

    def test_setDec_positive(self):
        resp = self.emu.processComand(':Sd +45*30:00.00#')
        self.assertEqual(resp, '1', f"Set positive DEC should return '1', got '{resp}'")

    def test_setDec_negative(self):
        resp = self.emu.processComand(':Sd -16*42:58.00#')
        self.assertEqual(resp, '1', f"Set negative DEC should return '1', got '{resp}'")

    def test_setDec_updates_lastDec(self):
        self.emu.processComand(':Sd +45*30:00.00#')
        self.assertEqual(len(self.emu.lastDec), 3)
        self.assertEqual(self.emu.lastDec[0], 45)
        self.assertEqual(self.emu.lastDec[1], 30)

    # --- GOTO ---

    def test_goto_MS_after_set_RA_DEC(self):
        self.emu.processComand(':Sr 06:45:08.00#')
        self.emu.processComand(':Sd +45*30:00.00#')
        resp = self.emu.processComand(':MS#')
        # In testing mode move() returns '1' and MS responds '0' (slew accepted)
        self.assertIn(resp, ('0', '1'), f"Unexpected GOTO response: '{resp}'")

    def test_goto_updates_position(self):
        ra_orig = self.emu.zeq25data.getRA()
        self.emu.processComand(':Sr 06:45:08.00#')
        self.emu.processComand(':Sd -16*42:58.00#')
        self.emu.processComand(':MS#')
        ra_nuevo = self.emu.zeq25data.getRA()
        # RA should have changed after move() in testing mode
        self.assertNotEqual(ra_orig, ra_nuevo)

    # --- Fecha y hora con arrow ---

    def test_getDate_GC_format(self):
        resp = self.emu.processComand(':GC#')
        self.assertTrue(resp.endswith('#'), f"Fecha no termina en '#': '{resp}'")
        fecha = resp.rstrip('#')
        # Format MM/DD/YY → 3 parts separated by '/'
        parts = fecha.split('/')
        self.assertEqual(len(parts), 3, f"Malformed date: '{fecha}'")

    def test_getTime_GL_format(self):
        resp = self.emu.processComand(':GL#')
        self.assertTrue(resp.endswith('#'))
        hora = resp.rstrip('#')
        parts = hora.split(':')
        self.assertEqual(len(parts), 3, f"Malformed time: '{hora}'")

    def test_getSiderealTime_GS_format(self):
        resp = self.emu.processComand(':GS#')
        self.assertTrue(resp.endswith('#'))
        parts = resp.rstrip('#').split(':')
        self.assertEqual(len(parts), 3)

    def test_getGMTOffset_GG_format(self):
        resp = self.emu.processComand(':GG#')
        self.assertTrue(resp.endswith('#'))
        offset = resp.rstrip('#')
        # Debe ser [+-]HH:MM
        self.assertRegex(offset, r'^[+\-]\d{2}:\d{2}$',
                         f"Malformed GMT offset: '{offset}'")

    def test_getDate_uses_arrow_current_year(self):
        resp = self.emu.processComand(':GC#')
        fecha = resp.rstrip('#')          # MM/DD/YY
        yy = int(fecha.split('/')[2])
        current_year = arrow.now().year % 100
        self.assertEqual(yy, current_year,
                         f"Year in date '{fecha}' does not match current year")

    # --- GoHome ---

    def test_goHome_MH(self):
        resp = self.emu.processComand(':MH#')
        self.assertEqual(resp, '1')

    # --- Tracking ---

    def test_tracking_on(self):
        resp = self.emu.processComand(':ST1#')
        self.assertEqual(resp, '1')

    def test_tracking_off(self):
        resp = self.emu.processComand(':ST0#')
        self.assertEqual(resp, '1')

    def test_isSlewing_SE(self):
        resp = self.emu.processComand(':SE?#')
        self.assertIn(resp, ('0', '1'))


# ===========================================================================
# Tests de ObservationList
# ===========================================================================

class TestObservationList(unittest.TestCase):

    def setUp(self):
        self.lista = ObservationList()

    def test_add_and_show(self):
        self.lista.add('23:22:20#', '-32*08:03#')
        self.assertEqual(len(self.lista.listCoords), 1)
        ra, dec = self.lista.listCoords[0]
        self.assertNotIn('#', ra,  "add() should strip '#' from RA")
        self.assertNotIn('#', dec, "add() should strip '#' from DEC")

    def test_add_without_hash(self):
        self.lista.add('23:22:20', '-32*08:03')
        self.assertEqual(len(self.lista.listCoords), 1)

    def test_delete(self):
        self.lista.add('23:22:20', '-32*08:03')
        self.lista.add('06:45:08', '+45*30:00')
        self.lista.delete(0)
        self.assertEqual(len(self.lista.listCoords), 1)
        self.assertEqual(self.lista.listCoords[0][0], '06:45:08')

    def test_pop(self):
        self.lista.add('23:22:20', '-32*08:03')
        self.lista.add('06:45:08', '+45*30:00')
        self.lista.pop()
        self.assertEqual(len(self.lista.listCoords), 1)

    def test_clearList(self):
        self.lista.add('23:22:20', '-32*08:03')
        self.lista.clearList()
        self.assertEqual(len(self.lista.listCoords), 0)

    def test_setNameFile(self):
        self.lista.setNameFile('mi_sesion')
        self.assertEqual(self.lista.nameFile, 'mi_sesion')

    def test_setNameFile_empty_does_not_change(self):
        self.lista.setNameFile('original')
        self.lista.setNameFile('')
        self.assertEqual(self.lista.nameFile, 'original')

    def test_reset(self):
        self.lista.add('23:22:20', '-32*08:03')
        self.lista.setNameFile('sesion')
        self.lista.reset()
        self.assertEqual(len(self.lista.listCoords), 0)
        self.assertEqual(self.lista.nameFile, '')

    def test_saveFile_crea_csv(self):
        import os
        import tempfile
        tmpdir = tempfile.mkdtemp()
        fname = os.path.join(tmpdir, 'test_obs')
        self.lista.setNameFile(fname)
        self.lista.add('23:22:20', '-32*08:03')
        self.lista.add('06:45:08', '+45*30:00')
        self.lista.saveFile()
        # saveFile() adds timestamp to the filename
        archivos = os.listdir(tmpdir)
        csv_files = [f for f in archivos if f.endswith('.csv')]
        self.assertEqual(len(csv_files), 1, "Should create exactly one CSV")
        with open(os.path.join(tmpdir, csv_files[0])) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        self.assertIn('23:22:20', lines[0])
        # After saveFile() the list is empty
        self.assertEqual(len(self.lista.listCoords), 0)


# ===========================================================================
# Integration tests – real TCP server
# ===========================================================================

class TestSocketServer(unittest.TestCase):
    """
    Starts a minimal threaded server using EmulZeq directly
    and verifies TCP communication.
    """

    PORT = 14000   # test port, different from production port

    @classmethod
    def setUpClass(cls):
        cls.emu = EmulZeq(testing=True)
        cls._stop = threading.Event()

        cls._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cls._srv.bind(('127.0.0.1', cls.PORT))
        cls._srv.listen(5)
        cls._srv.settimeout(1.0)

        def _serve():
            while not cls._stop.is_set():
                try:
                    conn, _ = cls._srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    data = conn.recv(1024)
                    if data:
                        cmd = data.decode('utf-8', errors='replace').strip()
                        reply = cls.emu.processComand(cmd)
                        if reply:
                            conn.sendall(reply.encode('utf-8'))
                finally:
                    conn.close()

        cls._thread = threading.Thread(target=_serve, daemon=True)
        cls._thread.start()
        time.sleep(0.1)   # give the server time to start

    @classmethod
    def tearDownClass(cls):
        cls._stop.set()
        cls._srv.close()
        cls._thread.join(timeout=2)

    def _cmd(self, command: str, timeout: float = 2.0) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(('127.0.0.1', self.PORT))
            s.sendall(command.encode('utf-8'))
            try:
                return s.recv(1024).decode('utf-8', errors='replace')
            except socket.timeout:
                return ''

    def test_socket_getVersion(self):
        resp = self._cmd(':V#')
        self.assertTrue(resp.startswith('V'), f"Expected 'V...', got '{resp}'")

    def test_socket_getMountInfo(self):
        resp = self._cmd(':MountInfo#')
        self.assertIn(resp, ('8407', '8408', '8497', '8498'))

    def test_socket_getRA(self):
        resp = self._cmd(':GR#')
        self.assertTrue(resp.endswith('#'))
        self.assertEqual(len(resp.rstrip('#').split(':')), 3)

    def test_socket_getDec(self):
        resp = self._cmd(':GD#')
        self.assertTrue(resp.endswith('#'))
        self.assertIn('*', resp)

    def test_socket_setRA_and_getDec(self):
        resp_set = self._cmd(':Sr 10:30:00.00#')
        self.assertEqual(resp_set, '1')

    def test_socket_setDec(self):
        resp_set = self._cmd(':Sd +30*15:00.00#')
        self.assertEqual(resp_set, '1')

    def test_socket_goto_full_flow(self):
        self._cmd(':Sr 10:30:00.00#')
        self._cmd(':Sd +30*15:00.00#')
        resp = self._cmd(':MS#')
        self.assertIn(resp, ('0', '1'))

    def test_socket_getDate_arrow(self):
        resp = self._cmd(':GC#')
        self.assertTrue(resp.endswith('#'))
        parts = resp.rstrip('#').split('/')
        self.assertEqual(len(parts), 3)

    def test_socket_getTime_arrow(self):
        resp = self._cmd(':GL#')
        self.assertTrue(resp.endswith('#'))
        parts = resp.rstrip('#').split(':')
        self.assertEqual(len(parts), 3)

    def test_socket_unknown_command_no_crash(self):
        resp = self._cmd(':XX#')
        # Should not crash the server, response may be empty
        self.assertIsInstance(resp, str)

    def test_socket_multiple_sequential_clients(self):
        for i in range(5):
            resp = self._cmd(':V#')
            self.assertTrue(resp.startswith('V'), f"Failed on iteration {i}")


# ===========================================================================

if __name__ == '__main__':
    unittest.main(verbosity=2)
