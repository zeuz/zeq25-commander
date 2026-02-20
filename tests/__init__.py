import unittest
from zeq25 import Zeq25

class BaseEndpointTestCase(unittest.TestCase):
    montura = Zeq25('/dev/ttyUSB1', True)
