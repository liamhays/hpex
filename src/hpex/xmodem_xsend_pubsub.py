import os
import math
import time
from pathlib import Path

import xmodem
from pubsub import pub
import serial

from hpex.settings import HPexSettingsTools
from hpex.hp_variable import HPVariable
from hpex.helpers import KermitProcessTools, XModemProcessTools # needed for checksum_to_hexstr

# Although there is a bit of duplicate code, putting this here as a
# separate class keeps XModemConnector smaller and reduces the already
# distressingly large argument list it requires.

class XModemXSendConnector:
    def getc(self, size, timeout=.1):
        #print('getc')
        return self.ser.read(size) or None
                    
    def putc(self, data, timeout=.1):
        #print('putc')
        return self.ser.write(data) or None

    # fname is either a string (file to get or receive), or if command
    # == 'disconnect', a temporary file that contains the original path.
    def run(self, port, parent, fname, ptopic,
            use_callafter=True, alt_options=None): # ptopic for parent
        if use_callafter:
            # So this is kind of a kludge. We don't want to globally
            # import wx if we're running in the CLI, to keep it light
            # and fast, but we can't conditionally globally
            # import. However, we /can/ import wx in each and every
            # function that needs it, _if and only if_
            # self.use_callafter is true. This is because the only
            # thing this class (and KermitConnector) uses wx for is
            # CallAfter, for thread-safety.
            import wx
            
        # I don't think it's readily possible to receive files over
        # XModem. I won't add that feature, then, at least for now.
        self.port = port
        self.parent = parent
        self.fname = fname
        #self.command = command
        self.ptopic = ptopic
        self.use_callafter = use_callafter
        #self.current_path = current_path
        # this tells the receiver frame whether or not to update the
        # progress bar
        self.should_update = True

        self.ser_timeout = 3
            
        #self.cancelled = False

        # 128 bytes per XModem packet, and we round up.
        self.packet_count = math.ceil(
            os.path.getsize(self.fname) / 128)


        # assemble options for serial port
        if not alt_options:
            settings = HPexSettingsTools.load_settings()
        else:
            settings = alt_options
        baud = settings['baud_rate']
        parity = None
        if settings['parity'] == '0 (None)':
            parity = serial.PARITY_NONE
        elif settings['parity'] == '1 (Odd)':
            parity = serial.PARITY_ODD
        elif settings['parity'] == '2 (Even)':
            parity = serial.PARITY_EVEN
        elif settings['parity'] == '3 (Mark)':
            parity = serial.PARITY_MARK
        elif settings['parity'] == '4 (Space)':
            parity = serial.PARITY_SPACE

        try:
            self.ser = serial.Serial(
                # short timeout so we get something like what Kermit
                # has
                port, baud, parity=parity, timeout=self.ser_timeout, write_timeout=self.ser_timeout)
            self.modem = xmodem.XMODEM(self.getc, self.putc)
        except Exception as e:
            print(e)
            #print('xmodem failed at serial port opening')

            if self.use_callafter:
                # no data
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.serial_port_error.{self.ptopic}')
            else:
                pub.sendMessage(
                    f'xmodem.serial_port_error.{self.ptopic}')
                
            return
        print('sending file')
        # send_connect means that HPex is connected to the XModem server
        try:
            self.ser.flush()
            self.stream = open(fname, 'rb')
            # One issue (slightly odd) that can arise is that after a
            # cancelled send, XModem is still trying to send to the
            # calculator. This makes connecting fail, because there's
            # a serial conflict (maybe) or the modem receives invalid
            # data.

            # Reducing the retry count (which should maybe even be
            # 1---we'll see) helps fix that: the modem just errors out.
            self.success = self.modem.send(
                self.stream, retry=1, timeout=self.ser_timeout,
                quiet=True, callback=self.callback)
            
        except:
            # we probably won't get here, but if we do, we still can
            # throw an error in the calling dialog
            print('xmodem failed at modem send')
            
            if self.use_callafter:
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.failed.{self.ptopic}')
            else:
                pub.sendMessage(f'xmodem.failed.{self.ptopic}')
                
                self.stream.close()
                
                return

        #if not self.success and not self.cancelled:
        if not self.cancelled:
            #print('not self.success and not self.cancelled')
            if self.use_callafter:
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.failed.{self.ptopic}')
            else:
                pub.sendMessage(f'xmodem.failed.{self.ptopic}')
                
            self.stream.close()

            
    def callback(self, total_packets, success_count, error_count):
        if self.use_callafter:
            import wx
        #print(total_packets, success_count)
        if success_count == self.packet_count: # done

            if self.use_callafter:
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.done.{self.ptopic}',
                    file_count=self.packet_count,
                    total=total_packets,
                    success=success_count,
                    error=error_count)

            else:
                pub.sendMessage(
                    f'xmodem.done.{self.ptopic}',
                    file_count=self.packet_count,
                    total=total_packets,
                    success=success_count,
                    error=error_count)

#            if self.delete_after_send:
#                os.remove(self.fname)

        else:

            if self.use_callafter:
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.newdata.{self.ptopic}',
                    file_count=self.packet_count,
                    total=total_packets,
                    success=success_count,
                    error=error_count,
                    should_update=self.should_update)

            else:
                pub.sendMessage(
                    f'xmodem.newdata.{self.ptopic}',
                    file_count=self.packet_count,
                    total=total_packets,
                    success=success_count,
                    error=error_count,
                    should_update=self.should_update)


    def cancel(self):
        self.cancelled = True
        self.should_update = False
        self.modem.abort(timeout=1)

        if self.use_callafter:
            import wx
            wx.CallAfter(
                pub.sendMessage,
                f'xmodem.cancelled.{self.ptopic}',
                file_count=self.packet_count)

        else:
            pub.sendMessage(
                f'xmodem.cancelled.{self.ptopic}',
                file_count=self.packet_count)
