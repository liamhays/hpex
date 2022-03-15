import os
import math

import xmodem
from pubsub import pub

import serial

from settings import HPexSettingsTools

class XModemConnector:
    def getc(self, size, timeout=.1):
        return self.ser.read(size) or None
                    
    def putc(self, data, timeout=.1):
        return self.ser.write(data) or None
        
    def run(self, port, parent, fname, ptopic,
            use_callafter=True, alt_options=None): # ptopic for parent
        if use_callafter:
            # So this is kind of a kludge. We don't want to globally
            # import wx if we'r. running in the CLI, to keep it light
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
        self.ptopic = ptopic
        self.use_callafter = use_callafter
        # this tells the receiver frame whether or not to update the
        # progress bar
        self.should_update = True
        # an actual cancelled variable

        self.cancelled = False
        # 128 bytes per XModem packet, and we round up.
        self.packet_count = math.ceil(
            os.path.getsize(self.fname) / 128)
        #print('self.packet_count', self.packet_count)

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

        #print(port)
        #print(baud)
        #print(parity)
        #print(settings['parity'])
        # we aren't catching serial.serialutil.SerialExceptions
        try:
            self.ser = serial.Serial(
                # short timeout so we get something like what Kermit
                # has
                port, baud, parity=parity, timeout=2, write_timeout=2)
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
        # using a retry of 1 makes it quit instantly after failure,
        # which is really nice
        
        self.stream = open(fname, 'rb')
        try:
            self.success = self.modem.send(
                self.stream, retry=1, timeout=2,
                quiet=True, callback=self.send_callback)
        except:# Exception as e:
            #print(e)
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

        if not self.success and not self.cancelled:
            #print('not self.success and not self.cancelled')
            if self.use_callafter:
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.failed.{self.ptopic}')
            else:
                pub.sendMessage(f'xmodem.failed.{self.ptopic}')
                
        self.stream.close()
        self.ser.close()

    def send_callback(self, total_packets, success_count, error_count):
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
        self.modem.abort(timeout=2)

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
