import re
import time

try:
    import serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

try:
    import arrow
    _ARROW_AVAILABLE = True
except ImportError:
    _ARROW_AVAILABLE = False

class Zeq25:
    def __init__(self, device, testing = False):
        self.serial = None

        self._testing = testing
        self.currentSettings = dict()
        self.testDefaultSetting = {
            'Version' : 'V1.00',
            'FirmwareVersion1' : '010101020202',
            'FirmwareVersion2': '010101020202',
            'MountInfo': '8408',
            'currentOffsetGmt' : "+06:00",
            'currentDayLightSaving' : True,
            'currentLon' : '+101:00:59',
            'currentLat' : '22:59:00',
            'currentTime' : '22:00:00',
            'currentSideralTime' : '22:00:00',
            'currentDate' :  '04:01:18',
            'currentGuideRate': '1.23',
            'currentTrackingRate' : '0',
            'currentButtonMRate' : '5',
            'Dec' : "-32*08:03",
            'nextDec' : "-32*08:03",
            'RA' : "23:22:20",
            'nextRA' : "90:00:00",
            'tracking' : False

        }
        if self._testing:
            self.currentSettings = self.testDefaultSetting
        else:
            if not _SERIAL_AVAILABLE:
                raise RuntimeError("pyserial is not installed (pip install pyserial)")
            self.serial = serial.Serial(
                port=device,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=3.500,
                xonxoff=None,
                rtscts=False,
                write_timeout=None,
                dsrdtr=False
            )
    #write & read serial commands
    def writeCmd(self, command):
        if not self._testing:
            self.serial.write(command)

    def readStatus(self, numBytes):
        response = ''
        if not self._testing:
            response = self.serial.read(numBytes)
        return response

    def _validate_command(self, response):
        assert response.endswith('#'), 'Command failed'

    def _arrayStringToNum(self, array):
        ret = []
        for s in array:
            if s.find('.') >= 0:
                try:
                    val = float(s)
                except Exception:
                    val = 0
            else:
                try:
                    val = int(s)
                except Exception:
                    val = 0
            ret.append(val)
        return ret

    #Telescope Information

    #Sets the offset from Greenwich Mean Time (Exclude Daylight Saving Time)
    #:SG sHH:MM#
    def setOffsetGMT(self, hh,mm):
        command = ":SG %s:%s#" %(hh, mm)
        self.writeCmd(command)
        response = self.readStatus(1)
        self.currentSettings['currentOffsetGmt'] = '%s:%s' % (hh, mm)
        return response

    #Sets the status of Daylight Saving Time.
    def setDayLightSaving(self, bDLS):
        ret = False
        command = (":SDS0#", ":SDS1#") [bDLS]
        self.writeCmd(command)
        response = self.readStatus(1)
        self.currentSettings['currentDaylightSaving'] = bDLS
        if self._testing:
            ret = True
        else:
            assert response == '1'
            ret = True
        return  ret

    #Sets the current longitude
    def setCurrentLon(self, grad, min, secs):
        ret = False
        command = ":Sg %s*%s:%s#" % (grad, min, secs)
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = True
        else:
            assert response == '1'
            ret = True
        self.currentSettings['currentLon'] = "%s:%s:%s" % (grad, min, secs)
        return ret

    #Sets the current latitude
    def setCurrentLat(self, grad, min, secs):
        ret = False
        command = ":St %s*%s:%s#" % (grad, min, secs)
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = True
        else:
            assert response == '1'
            ret = True
        self.currentSettings['currentLat'] = "%s:%s:%s" % (grad, min, secs)
        return ret

    #Sets the current local time.
    def setCurrentTime(self, hh, min, secs):
        ret = False
        command = ":SL %s*%s:%s#" % (hh, min, secs)
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = True
        else:
            assert response == '1'
            ret = True
        return ret

    #Sets the current date
    def setCurrentDate(self, hh, min, secs):
        command = ":SC %s*%s:%s#" % (hh, min, secs)
        self.writeCmd(command)

    #Gets the offset from Greenwich Mean Time
    #Response: 'sHH:MM#'
    def getOffsetGMT(self):
        ret = ''
        command = ":GG#"
        self.writeCmd(command)
        response = self.readStatus(6)
        if self._testing:
           ret = self.currentSettings['currentOffsetGmt'] + '#'
        else:
            self._validate_command(response)
            ret = re.split(r'(\+\d+):(\d+)', response)
            ret.pop()
            ret.pop(0)
            ret = self._arrayStringToNum(ret)
        return ret

    #Gets the status of Daylight Saving Time
    #Response: '0'or '1'
    def getDayLightSaving(self):
        ret = ''
        command = ":GDS#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = "%d" % self.currentSettings['currentDayLightSaving']
        else:
            ret = response
        return ret

    #Gets the current longitude
    #Response: "sDDD*MM:SS#"
    def getCurrentLon(self):
        ret = ''
        command = ":Gg#"
        self.writeCmd(command)
        response = self.readStatus(11)

        if self._testing:
            ret = self.currentSettings['currentLon'] + '#'
        else:
            self._validate_command(response)
            ret = re.split(r'\*(\d+):(\d+.+)', response)
            ret.pop() # strip trailing '#'
            ret = self._arrayStringToNum(ret)
        return ret

    #Gets the current latitude
    #Response: "sDDD*MM:SS#"
    def getCurrentLat(self):
        ret = ''
        command = ":Gt#"
        self.writeCmd(command)
        response = self.readStatus(11)
        self._validate_command(response)
        if self._testing:
            ret = self.currentSettings['currentLat'] + '#'
        else:
            ret = re.split(r'\*(\d+):(\d+.+)', response)
            ret.pop()  # strip trailing '#'
            ret = self._arrayStringToNum(ret)
        return ret

    #Gets the current local time
    #Response: 'HH:MM:SS#'
    def getCurrentTime(self):
        ret = ''
        command = ":GL#"
        self.writeCmd(command)
        response = self.readStatus(9)
        self._validate_command(response)
        if self._testing:
            ret = self.currentSettings['currentTime'] + '#'
        else:
            #ret = re.split('(\d+):(\d+):(\d+)', response)
            ret = response[:-1]
        return ret

    # Gets the current Date
    # Response: 'MM:DD:YY#'
    def getCurrentDate(self):
        ret = ''
        command = ":GC#"
        self.writeCmd(command)
        response = self.readStatus(9)
        self._validate_command(response)
        if self._testing:
            ret = self.currentSettings['currentDate'] + '#'
        else:
            #ret = re.split('(\d+):(\d+):(\d+)', response)
            ret = response[:-1]
        return ret

    def getTimeObject(self):
        d = self.getCurrentDate()
        t = self.getCurrentTime()
        if _ARROW_AVAILABLE:
            ret = arrow.get("%s %s" % (d, t), "MM/DD/YY HH:MM:SS")
        else:
            ret = time.strptime("%s %s" % (d, t), "%m/%d/%y %H:%M:%S")
        return ret

    #Gets the current sideral time
    #Response: 'HH:MM:SS#'
    def getCurrentSideralTime(self):
        ret = ''
        command = ":GS#"
        self.writeCmd(command)
        response = self.readStatus(9)
        self._validate_command(response)
        if self._testing:
            ret = self.currentSettings['currentSideralTime'] + '#'
        else:
            ret = response[:-1]
        return ret

    #Gets the current Right Ascension
    #Response: 'sDD:MM:SS#'
    def getRA(self):
        ret = ''
        command = ":GR#"
        self.writeCmd(command)
        if self._testing:
            ret = self.currentSettings['RA'] + '#'

        else:
            response = self.readStatus(10)
            self._validate_command(response)
            ret = re.split(r'(\d+):(\d+):(\d+.+)', response[:-1])
            ret.pop(0)
            ret.pop()  # strip trailing '#'
            ret = self._arrayStringToNum(ret)
        return ret

    # Gets the current Right Ascension
    # Response: 'sDD*MM:SS#'
    def getDec(self):
        ret = ''
        command = ":GD#"
        self.writeCmd(command)
        if self._testing:
            ret = self.currentSettings['Dec'] + '#'

        else:
            response = self.readStatus(10)
            self._validate_command(response)
            ret = re.split(r'\*(\d+):(\d+.+)', response[:-1])
            ret.pop()  # strip trailing '#'
            ret = self._arrayStringToNum(ret)
        return ret

    # Gets the current Right Ascension
    # Response: 'sDD*MM:SS#'
    def getAltitude(self):
        ret = ''
        command = ":GA#"
        self.writeCmd(command)
        if self._testing:
            ret = self.currentSettings['Altitude'] + '#'
        else:
            response = self.readStatus(10)
            self._validate_command(response)
            ret = re.split(r'\*(\d+):(\d+.+)', response[:-1])
            ret.pop()  # strip trailing '#'
            ret = self._arrayStringToNum(ret)
        return ret

    # Gets the current Right Ascension
    # Response: 'sDD*MM:SS#'
    def getAzimuth(self):
        ret = ''
        command = ":GZ#"
        self.writeCmd(command)

        if self._testing:
            ret = self.currentSettings['Azimuth'] + '#'
        else:
            response = self.readStatus(10)
            self._validate_command(response)
            ret = re.split(r'\*(\d+):(\d+)', response[:-1])
            ret.pop()  # strip trailing '#'
            ret = self._arrayStringToNum(ret)
        return ret

    #--- Miscellaneus Information:
    # Gets the current Version
    # Response: 'V1.00#'
    def getVersion(self):
        ret = ''
        command = ":V#"
        self.writeCmd(command)
        if self._testing:
            ret = self.currentSettings['Version'] + '#'
        else:
            response = self.readStatus(6)
            self._validate_command(response)
            ret = response[:-1]
        return ret

    #Gets the date of the mainboards and the hand controllers firmware
    #Response: "YYMMDDYYMMDD#"
    def getFirmwareVersion(self):
        ret = ''
        command = ":FW1#"
        self.writeCmd(command)
        response = self.readStatus(13)
        if self._testing:
            ret = self.currentSettings['FirmwareVersion1'] + '#'
        else:
            self._validate_command(response)
            ret = response[:-1]
        return ret


    #Gets the date of the RA motor boards and the DEC motor boards firmware
    #Response: "YYMMDDYYMMDD#"
    def getFirmwareMotorVersion(self):
        ret = ''
        command = ":FW2#"
        self.writeCmd(command)
        response = self.readStatus(13)
        if self._testing:
            ret = self.currentSettings['FirmwareVersion2'] + '#'
        else:
            self._validate_command(response)
            ret = response[:-1]
        return ret

    #This command gets the mount type
    #Response: "8407", "8497", "8408", "8498"
    #This command gets the mount type. "8407" means iEQ45 EQ mode or iEQ30, "8497"
    ## means iEQ45 AA mode, "8408" means ZEQ25, ""498" means SmartEQ.
    def getMountInfo(self):
        ret = ''
        command = ":MountInfo#"
        self.writeCmd(command)
        response = self.readStatus(4)
        if self._testing:
            ret = self.currentSettings['MountInfo']
        else:
            ret = response
        return ret
    """
    ###########
    ##
    # --- Telescope Motion:
    ###
    """
    #Slew to the most recently defined RA and DEC coordinates or most recently defined
    def move(self):
        ret = ''
        command = ":MS#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['RA'] = self.currentSettings['nextRA']
            self.currentSettings['Dec'] = self.currentSettings['nextDec']
            ret = '1'
        else:
            ret = response
        return ret

    #This command get the slewing status.
    #
    def isSlewing(self):
        ret = False
        command = ":SE?#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            response = '1'
        if response=='1':
            ret = True
        return ret

    def stop(self):
        ret = ''
        command = "Q#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = '1'
        else:
            ret = response
        return ret

    #Move to direction [n,s,e,w] for n Msecs
    def moveDirectionMsecs(self, Msecs, direction):
        command = ":M%c%s#" % (direction, Msecs)
        self.writeCmd(command)

    #Get guide rate
    #Response: "n.nn#"
    def getGuideRate(self):
        ret = ''
        command = ":AG#"
        self.writeCmd(command)
        response = self.readStatus(5)
        if self._testing:
            ret = self.currentSettings['currentGuideRate'] + "#"
        else:
            ret = response[:-1]
        return ret

    #Selects guide rate nnn*0.01x sidereal rate. nnn is in the range of 10 to 90, and 100.
    def selectGuideRate(self, rate):
        ret = ''
        command = ":RG%d#" % rate
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = '1'
        else:
            ret = response
        return ret


    #These command sets tracking state. ":ST0#" indicates stop tracking, ":ST1#" indicates start tracking.
    #Response : "1"
    def startTracking(self):
        ret = ''
        command = ":ST1#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['tracking'] = True
            ret = '1'
        else:
            ret = response
        return ret

    def stopTracking(self):
        ret = ''
        command = ":ST0#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['tracking'] = False
            ret = '1'
        else:
            ret = response
        return ret

    def isTracking(self):
        ret = False
        command = ":AT#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = self.currentSettings['tracking']
        if response == '1':
            ret = True
        return ret

    #gets the tracking rate
    #Response: "0" Sidereal "1" Lunar "2" Solar "3" King rate "4" Custom Rate
    def getTrackingRate(self):
        ret = ''
        command = ":SQT#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = self.currentSettings['currentTrackingRate']
        else:
            ret = response
        return ret

    # sets the tracking rate
    # Response: "0" Sidereal "1" Lunar "2" Solar "3" King rate "4" Custom Rate
    def setTrackingRate(self, rate):
        ret = ''
        command = ":RT%d#" % rate
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['currentTrackingRate'] = rate
            ret = '1'
        else:
            ret = response
        return ret

    def isParking(self):
        ret = False
        command = ":AP#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            #response = '1'
            response = ('0','1') [self.currentSettings['parking']]
        if response == '1':
            ret = True
        return ret

    def unPark(self):
        ret = ''
        command = ":MP0#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['parking'] = False
            ret = '1'
        else:
            ret = response
        return ret

    def Park(self):
        ret = ''
        command = ":MP1#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['parking'] = True
            ret = '1'
        else:
            ret = response
        return ret

    #This command returns the side of the pier on which the telescope is currently positioned
    #Response 0: East , 1: West
    def getSidePier(self):
        ret = ''
        command = ":MP1#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = '1'
        else:
            ret = response
        return ret

    #This command returns whether the telescope is at "home" position.
    def goHome(self):
        ret = ''
        command = ":MH#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = '1'
        else:
            ret = response
        return ret

    """
    Sets the moving rate used for the N-S-E-W buttons. 
    For n, specify an integer from 1 to 9. 1 stands for 1x sidereal tracking rate, 2 stands for 2x, 3 stands for 8x,
    4 stands for 16x, 5 stands for 64x, 6 stands for 128x, 7 stands for 256x, 8 stands for 512x,
    9 stands for maximum speed(larger than 512x).
    """
    def setButtonMovingRate(self, rate):
        ret = ''
        command = ":SR%d#" % rate
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = '1'
        else:
            ret = response
        if ret == '1':
            self.currentSettings['currentButtonMRate'] = rate
        return ret

    #Set custom rate tracking on RA
    #:RR snn.nnnn#
    #Response 1
    def setCustomRateTrackingRA(self, rate):
        ret = False
        command = ":RR %.4f#" % rate
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['CustomRateTrackingRA'] = rate
            ret = '1'
        else:
            assert response == '1'
            ret = True
        return ret

    # Set custom rate tracking on DEC
    #:RR snn.nnnn#
    # Response 1
    def setCustomRateTrackingDEC(self, rate):
        ret = False
        command = ":RD %.4f#" % rate
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['CustomRateTrackingDEC'] = rate
            ret = '1'
        else:
            assert response == '1'
            ret = True
        return ret

    #Gets the moving rate used for the N-S-E-W buttons
    #Response: "n#"
    def getButtonMovingRate(self):
        ret = ''
        command = ":Gr#"
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            ret = self.currentSettings['currentButtonMRate']
        else:
            self.currentSettings['currentButtonMRate'] = response
            ret = response
        return ret

    """
    ###########
    ##
    # --- Telescope Position:
    ###
    """
    def setRA(self, hh, mm, secs):
        ret = False
        command = ":Sr %02d:%02d:%.2f#" % (hh, mm, secs)
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['nextRA'] = "%02d:%02d:%.2f" % (hh, mm, secs)
            ret = True
        if response == '1':
            self.currentSettings['nextRA'] = "%02d:%02d:%.2f" % (hh, mm, secs)
            assert response == '1'
            ret = True
        return ret

    def setDec(self, hh, mm, secs):
        ret = False
        sign = '-'
        if hh>=0:
            sign = '+'
        command = ":Sd %c%02d*%02d:%.2f#" % (sign, hh, mm, secs)
        self.writeCmd(command)
        response = self.readStatus(1)
        if self._testing:
            self.currentSettings['nextDec'] = "%02d:%02d:%.2f" % (hh, mm, secs)
            ret = True
        if response == '1':
            self.currentSettings['nextDec'] = "%02d:%02d:%.2f" % (hh, mm, secs)
            assert response == '1'
            ret = True
        return ret

    """
    aRA = Array [hh, min, secs]  
    aDec = Array [hh, min, secs]
    """

    def MoveToRADec(self, aRA, aDec):
        self.setRA(aRA[0], aRA[1], aRA[2])
        self.setDec(aDec[0], aDec[1], aDec[2])
        self.move()

    def waitMove(self):
        cont = 0
        while self.isSlewing():
            cont +=1
