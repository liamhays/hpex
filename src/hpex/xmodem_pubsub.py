import os
import math
import time
from pathlib import Path
import tempfile

import xmodem
from pubsub import pub
import serial

from hpex.settings import HPexSettingsTools
from hpex.hp_variable import HPVariable
from hpex.helpers import KermitProcessTools # needed for checksum_to_hexstr

# TODO: when connecting, the statusbar should be updated (because it
# can be slow)---unless the above todo makes this irrelevant

# TODO: test what the output of Conn4x gives---do the received files
# have the extra \x00 bytes at the end?
ACK = b'\x06'
class XModemConnector:
    def getc(self, size, timeout=.1):
        #print('getc')
        return self.ser.read(size) or None
                    
    def putc(self, data, timeout=.1):
        #print('putc')
        return self.ser.write(data) or None

    # fname is either a string (file to get or receive), or if command
    # == 'disconnect', a temporary file that contains the original path.
    def run(self, port, parent, fname, command, short_timeout, current_path, ptopic,
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
        self.command = command
        self.ptopic = ptopic
        self.use_callafter = use_callafter
        self.current_path = current_path
        # this tells the receiver frame whether or not to update the
        # progress bar
        self.should_update = True
        # an actual cancelled variable

        if short_timeout == True:
            # if connected to XModem server, use shorter timeouts
            self.ser_timeout = .5
        else:
            self.ser_timeout = 3
            
        self.cancelled = False
        if self.command == 'send_connect' or self.command == 'send':
            print('send or send_connect, self.fname is', self.fname)
            print('cwd is', os.getcwd())
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

        #print(port)
        #print(baud)
        #print(parity)
        #print(settings['parity'])
        # we aren't catching serial.serialutil.SerialExceptions
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
        # using a retry of 1 makes it quit instantly after failure,
        # which is really nice

        # now we process the command
        if command == 'connect':
            self.connect_to_server()
        elif command == 'disconnect':
            self.disconnect_from_server(fname)
        elif command == 'refresh':
            # run M and L
            memory, objects = self.run_M_L()
            # prevent the caller trying to access the variables on failure
            if memory != -1 and objects != None:
                wx.CallAfter(
                    pub.sendMessage, 
                    f'xmodem.refreshdone.{self.ptopic}',
                    mem=int(memory), 
                    #server_verstring=version.decode('utf-8'),
                    varlist=objects)
            
        elif command == 'send_connect':
            print('sending file, send_connect')
            # send_connect means that HPex is connected to the XModem server
            try:
                self.ser.flush()
                self.sendCommand(b'P')
                self.sendCommandPacket(Path(fname).name)
                self.stream = open(fname, 'rb')
                self.success = self.modem.send(
                    self.stream, retry=9, timeout=1,
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

            if not self.success and not self.cancelled:
                #print('not self.success and not self.cancelled')
                if self.use_callafter:
                    wx.CallAfter(
                        pub.sendMessage,
                        f'xmodem.failed.{self.ptopic}')
                else:
                    pub.sendMessage(f'xmodem.failed.{self.ptopic}')
                
            self.stream.close()
        elif command == 'get_connect':
            try:
                self.ser.flush()
                self.sendCommand(b'G')
                self.sendCommandPacket(fname)
                self.stream = open(Path(self.current_path,fname), 'wb')
                # when receiving, success is zero on failure or bytes
                # successfully sent. We just have to assume that
                # non-zero is success
                self.success = self.modem.recv(
                    self.stream, retry=9, timeout=1,
                    quiet=False)
                if self.use_callafter:
                    wx.CallAfter(
                        pub.sendMessage,
                        f'xmodem.done.{self.ptopic}')                
                else:
                    pub.sendMessage(
                        f'xmodem.done.{self.ptopic}')

                print('after modem.recv')
            except:
                # we probably won't get here, but if we do, we still can
                # throw an error in the calling dialog
                print('xmodem failed at modem recv')
                
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

    def checksumStr(self, s: str) -> int:
        result = 0
        for i in s:
            result += ord(i)
        return result

    def checksumBytes(self, s: bytes) -> int:
        result = 0
        for i in s:
            result += i
        return result
    
    def sendCommand(self, s: bytes):
        """Send command s to the XModem server."""

        self.ser.write(s)


    def sendCommandPacket(self, instr: str):
        """Send command packet s to the XModem server and wait for ACK."""
        c = b''

        # We have to construct it like this, otherwise extra bytes get
        # added for no apparent reason
        s = bytearray()
        s.append((len(instr) & 0xff00) >> 8)
        s.append((len(instr) & 0xff))
        s.extend(bytearray(instr, 'utf-8'))
        s.append(self.checksumStr(instr) & 0xff)

        self.ser.write(s)
        self.ser.flush()
        c = self.ser.read()
        while c != ACK:
            c = self.ser.read()
            print(c)

        print('command packet successfully sent')

    def getCommandPacket(self) -> bytes:
        self.ser.flush()
        # read the size packet
        size_packet = self.ser.read(2)
        if len(size_packet) == 2:
            # maybe something in here that limits the length to 10000
            # it's in YModem.pas
            size = size_packet[0] * 256 + size_packet[1]
            print('packet size', size)
            # now read as many bytes as specified in the size packet
            data = self.ser.read(size)
            print('packet data', data)
            # finally, read the checksum of the data and check it
            chk = self.ser.read(1)
            print('chk, checksumXY:', hex(ord(chk)), hex(self.checksumBytes(data) & 0xff))
            if ord(chk) == (self.checksumBytes(data) & 0xff):
                # data is valid
                self.ser.write(ACK)
                self.ser.flush()
                return data
        return None

    def failure(self):
        cmd = self.command
        if self.use_callafter:
            import wx
            wx.CallAfter(
                pub.sendMessage,
                # this message will only ever be received by HPex
                f'xmodem.failed.{self.ptopic}',
                cmd=cmd)
                
        else:
            pub.sendMessage(
                f'xmodem.failed.{self.ptopic}',
                cmd=cmd)
                


    def clear_extra_bytes(self):
        """Read from self.ser until there is no more data."""
        r = self.ser.read()        
        # read all the extra packets sent
        while r != b'':
            self.ser.write(ACK)
            self.ser.flush()
            r = self.ser.read()



        
    def run_V(self):
        # increases reliability like in run_M_L

        # Now get the version of the XModem server
        try:
            self.clear_extra_bytes()
            self.sendCommand(b'V')
            version = self.getCommandPacket()
            print('version', version)
            self.clear_extra_bytes()
        except:
            self.failure()
            return None

        # don't need a special 'if version == None' here because
        # there's only one return value
        return version

    def get_hp_path(self):
        tmp = tempfile.TemporaryFile()
        try:
            self.clear_extra_bytes()
            self.sendCommand(b'E')
            self.sendCommandPacket("PATH '$$$p' STO")
            self.clear_extra_bytes()
            self.sendCommand(b'G')
            self.sendCommandPacket('$$$p')
            self.success = self.modem.recv(
                tmp, retry=9, timeout=1,
                quiet=False)
            #if self.success:
            #    self.clear_extra_bytes()
            #    self.sendCommand(b'E')
            #    self.sendCommandPacket("'$$$p' PURGE")
            return tmp
        except:
            print('failed to get path')
            self.failure()
            return None
    def run_M_L(self):
        print('run_M_L')
        if self.use_callafter:
            import wx
        # Start by getting the free memory. As far as I can tell, this
        # stuff has to be done in a specific order for it all to work
        # right.

        try:
            self.clear_extra_bytes()
            self.sendCommand(b'M')
            memory = self.getCommandPacket()
            print('memory in try', memory)
            self.clear_extra_bytes()
        except:
            self.failure()
            return -1, None # prevent unpack errors on failure, -1 is meaningless
            # also prevent int(None), which errors
            
        # Even if nothing errors out, reading data from the server can
        # still fail.
        if memory == None:
            self.failure()
            return -1, None
        


        # Finally, get the listing of the current directory.

        try:
            self.clear_extra_bytes()
            self.sendCommand(b'L')
            self.ser.flush()
            time.sleep(.3)
            l = self.getCommandPacket()
        except:
            self.failure()
            return -1, None

        if l == None:
            self.failure()
            return -1, None
        
        index = 0
        print(len(l))
        objects = []
        # process for later
        while index < len(l):
            # 1st byte is object name length
            # n bytes following are object name
            # 2 bytes are object prolog
            # 3 bytes are object size
            # 2 bytes are HP CRC
            lsize = l[index]
            index += 1
            
            name = l[index:index + lsize]
            index += lsize
            
            prologstr = l[index:index + 2]
            prolog = hex(prologstr[1] * 256 + prologstr[0])
            index += 2
            
            # object size is 3 bytes, which encode the size of the
            # object multiplied by 2 (to account for nibbles)
            
            objsize = l[index:index + 3]
            size = objsize[2] * 65536 + objsize[1] * 256 + objsize[0]
            size /= 2
            index += 3
            
            objcrc = l[index:index + 2]
            crc = objcrc[1] * 256 + objcrc[0]
            index += 2

            objects.append(HPVariable(KermitProcessTools.bytes_to_utf8(name),
                                      str(size), str(prolog),
                                      KermitProcessTools.checksum_to_hexstr(crc)))

        return memory, objects

    def connect_to_server(self):
        import wx

        memory, objects = self.run_M_L()
        if HPexSettingsTools.load_settings()['reset_directory_on_disconnect']:
            pathfile = self.get_hp_path()
        else:
            pathfile = None
            
        version = self.run_V()
        print(memory, version, objects)
        wx.CallAfter(
            pub.sendMessage,
            f'xmodem.connectdone.{self.ptopic}',
            mem=int(memory),
            server_verstring=version.decode('utf-8'),
            pathfile=pathfile,
            varlist=objects)

    def disconnect_from_server(self, pathfile):

        import wx
        # Restore original directory if desired, and send command 'Q'
        # to quit server on calculator.
        try:
            self.clear_extra_bytes()
            if HPexSettingsTools.load_settings()['reset_directory_on_disconnect']:
                print('reset directory')
                self.sendCommand(b'P')
                self.sendCommandPacket("$$$p")
                # XModem.send does not automatically seek to the
                # beginning of the file
                pathfile.seek(0)
                self.success = self.modem.send(
                    pathfile, retry=9, timeout=1,
                    quiet=True)# no callback
                self.clear_extra_bytes()
                self.sendCommand(b'E')
                # DUP to duplicate the name, EVAL to get the variable
                # value, SWAP to swap between value and variable name,
                # PURGE to delete variable, EVAL to change path.
                self.sendCommandPacket("'$$$p' DUP EVAL SWAP PURGE EVAL")

            self.clear_extra_bytes()
            self.sendCommand(b'Q')
            
        except Exception as e:
            print(e)
            self.failure()
            return

        wx.CallAfter(
            pub.sendMessage,
            f'xmodem.disconnectdone.{self.ptopic}')
        
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
