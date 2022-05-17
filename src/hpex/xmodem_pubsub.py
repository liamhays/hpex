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
from hpex.helpers import KermitProcessTools, XModemProcessTools # needed for checksum_to_hexstr
from hpex.hp_xmodem import HPXModem
# TODO: test what the output of Conn4x gives---do the received files
# have the extra \x00 bytes at the end?

ACK = b'\x06'
class XModemConnector:
    def getc(self, size, timeout=.1):
        #print('getc', size)
        #data = self.ser.read(size)
        #print('data', data)
        return self.ser.read(size) or None
                    
    def putc(self, data, timeout=.1):
        #print('putc', data)
        return self.ser.write(data) or None

    # fname is either a string (file to get or receive), or if command
    # == 'disconnect', a temporary file that contains the original path.
    def run(self, port, parent, fname, command, current_path, ptopic,
            use_callafter=True, alt_options=None): # ptopic for parent
        if use_callafter:
            # So this is kind of a kludge. We don't want to globally
            # import wx if we're running in the CLI, to keep it light
            # and fast, but we can't conditionally globally
            # import. However, we /can/ import wx in each and every
            # function that needs it. This is because the only thing
            # this class (and KermitConnector) uses wx for is
            # CallAfter, for thread-safety.
            import wx
            
        # I don't think it's readily possible to receive files over
        # XModem. I won't add that feature, then, at least for now.
        self.port = port
        self.parent = parent
        self.fname = fname
        self.command = command
        self.current_path = current_path
        self.ptopic = ptopic
        self.use_callafter = use_callafter

        # this tells the receiver frame whether or not to update the
        # progress bar
        self.should_update = True
        # an actual cancelled variable

        # Sending 1029 bytes (one 1024-byte XModem packet) at 9600
        # baud takes .86 seconds.
        self.ser_timeout = 1

            
        self.cancelled = False
        if self.command == 'send_connect':
            # The issue with sending a zero-length file is that the
            # modem never calls the callback function.
            # This leaves us with a couple options:
            #  - Use a time-delay if length is 0 after opening the
            #    sending dialog and just close, because the send
            #    is successful
            #    But what if the send fails?
            #  - Prevent sending zero-length file with XModem.
            #    This would be easy to implement but it is an
            #    annoying arbitrary restriction.
            #    An explanation would soften it though.
            
            print('send_connect, self.fname is', self.fname)
            print('cwd is', os.getcwd())
            # 128 bytes per XModem packet, and we round up.
            self.packet_count = math.ceil(
                os.path.getsize(self.fname) / 128)


        # assemble options for serial port
        self.ser = serial.Serial()
        self.ser.port = port
        if not alt_options:
            settings = HPexSettingsTools.load_settings()
        else:
            settings = alt_options
        self.ser.baud = settings['baud_rate']

        if settings['parity'] == '0 (None)':
            self.ser.parity = serial.PARITY_NONE
        elif settings['parity'] == '1 (Odd)':
            self.ser.parity = serial.PARITY_ODD
        elif settings['parity'] == '2 (Even)':
            self.ser.parity = serial.PARITY_EVEN
        elif settings['parity'] == '3 (Mark)':
            self.ser.parity = serial.PARITY_MARK
        elif settings['parity'] == '4 (Space)':
            self.ser.parity = serial.PARITY_SPACE

        self.ser.timeout = self.ser_timeout # fine, slightly bad naming
        self.ser.write_timeout = self.ser_timeout
        
        # On Windows, trying to refresh after a file transfer results
        # in an Access Denied error. The way to avoid this is to try
        # to open the serial port repeatedly until it works.

        # TODO: this isn't working exactly right
        tries = 0
        while True:
            if tries == 4:
                print('xmodem failed at serial port open')
                # Too many tries, something is wrong
                self.failure()
                    
            try:
                self.ser.open()

            except Exception as e:
                #print(e)
                pass

            if self.ser.is_open:
                #print('open')
                break
            tries += 1
            
            return

        self.modem = xmodem.XMODEM(self.getc, self.putc)

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
                    varlist=objects)

        # So, we figured out how the special 'D'-mode XModem works and
        # wrote a class similar to xmodem.XMODEM that can send files.
        #
        # Personally, I like mine better :).
        elif command == 'send_connect':
            print('sending file, send_connect')
            # send_connect means that HPex is connected to the XModem server
            try:
                self.clear_extra_bytes()
                self.ser.flush()
                self.sendCommand(b'P')
                f = Path(fname)
                self.sendCommandPacket(f.name)
                self.modem = HPXModem(self.ser)
                self.success = self.modem.send(f.open('rb'), retry=4, callback=self.callback)
                
            except Exception as e:
                print(e)
                # we probably won't get here, but if we do, we still can
                # throw an error in the calling dialog
                print('xmodem failed at modem send')
                
                self.failure()
            
                return

            if not self.success and not self.cancelled:
                #print('not self.success and not self.cancelled')
                self.failure()
                
        elif 'get_connect' in command:
            # 'get_connect_overwrite' is passed by FileGetDialog, when
            # the user specifies that they would like to overwrite
            final_name = Path(self.current_path,fname).expanduser()
            original_name = final_name
            
            if command != 'get_connect_overwrite':
                counter = 1
                while final_name.exists():
                    # this is to emulate the weird non-collision
                    # filename that Kermit makes so that we don't need
                    # multiple dialog messages
                    final_name = Path(original_name.parent, original_name.name + '.~' + str(counter) + '~').expanduser()
                    print(final_name)
                    counter += 1

            try:
                self.ser.flush()
                self.sendCommand(b'G')
                self.sendCommandPacket(fname)
                self.stream = final_name.open('wb')
                # when receiving, success is zero on failure or bytes
                # successfully sent. We just have to assume that
                # non-zero is success
                self.success = self.modem.recv(
                    self.stream, retry=9, timeout=self.ser_timeout,
                    quiet=False)
                # Since you can't stop the modem easily, we can cancel
                # it on the other side.
                # TODO: do we need to though?

                # MUST CLOSE THE STREAM OR ELSE IT IS EMPTY ON LINUX
                # and possibly Windows, but it's definitely platform-dependent
                self.stream.close()
                if self.use_callafter and not self.cancelled:
                    wx.CallAfter(
                        pub.sendMessage,
                        f'xmodem.done.{self.ptopic}',
                        file_count=0,
                        total=0,
                        success=0,
                        error=0)                
                else:
                    pub.sendMessage(
                        f'xmodem.done.{self.ptopic}',
                        file_count=0,
                        total=0,
                        success=0,
                        error=0)

            except Exception as e:
                print(e)
                # we probably won't get here, but if we do, we still can
                # throw an error in the calling dialog
                #print('xmodem failed at modem recv')
                
                self.failure()
                self.stream.close()
            
                return

            if not self.success and not self.cancelled:
                #print('not self.success and not self.cancelled')
                self.failure()
                

        elif command == 'chdir':
            # fname is the directory to change to
            print('change to', fname)
            try:
                self.sendCommand(b'E')
                self.sendCommandPacket(fname)
            except:
                self.failure()
                return

            if not self.cancelled:
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.done.{self.ptopic}')
            
        elif command == 'updir':
            try:
                self.sendCommand(b'E')
                self.sendCommandPacket('UPDIR')
            except:
                self.failure()
                return
            
            if not self.cancelled:
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.done.{self.ptopic}')
            
        elif command == 'home':
            try:
                self.sendCommand(b'E')
                self.sendCommandPacket('HOME')
            except:
                self.failure()
                return

            if not self.cancelled:
                wx.CallAfter(
                    pub.sendMessage,
                    f'xmodem.done.{self.ptopic}')

        print('self.ser.close')
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
        retry_count = 0
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
        while c != ACK and not self.cancelled:
            if retry_count == 3:
                # too many retries, something is wrong
                self.failure()
                return
            
            c = self.ser.read()
            retry_count += 1
            print(c)


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
        # used to stop checking for ACK
        self.cancelled = True
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


    def get_hp_path(self):
        # this creates a file with mode w+b, for reading and writing.
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
                quiet=True)
            if self.success:
                self.clear_extra_bytes()
                self.sendCommand(b'E')
                self.sendCommandPacket("'$$$p' PURGE")
            return tmp
        except:
            print('failed to get path')
            self.failure()
            return None
        
    def run_M_L(self):
        print('run_M_L')
        if self.use_callafter:
            import wx

        # When dealing with the XModem server, we still need to be
        # able to cancel. However, we can't just call modem.abort(),
        # so before every operation, we check the value of
        # self.cancelled to see if we should still be working.
        
        if self.cancelled: return -1, None
        # Start by getting the free memory.
        try:
            self.clear_extra_bytes()
            self.ser.flush()
            self.sendCommand(b'M')
            # TODO: I think something is wrong with how we complete a transfer
            #time.sleep(.5)
            #self.ser.timeout = 3
            memory = self.getCommandPacket()
            print('memory in try', memory)
            #self.ser.timeout = self.ser_timeout
            self.clear_extra_bytes()
        except:
            self.failure()
            return -1, None # prevent unpack errors on failure, -1 is meaningless
            # also prevent int(None), which errors

        if self.cancelled: return -1, None
        # Even if nothing errors out, reading data from the server can
        # still fail.
        if memory == None:
            self.failure()
            return -1, None
        


        # Finally, get the listing of the current directory.
        if self.cancelled: return -1, None
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
            if self.cancelled: return -1, None
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
            prolog = prologstr[1] * 256 + prologstr[0]
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
            
            objects.append(HPVariable(XModemProcessTools.bytes_to_utf8(name),
                                      str(size),
                                      XModemProcessTools.prolog_to_type(prolog),
                                      KermitProcessTools.checksum_to_hexstr(crc)))

        return memory, objects

    def connect_to_server(self):
        import wx
        # Home the calculator
        self.sendCommand(b'E')
        self.sendCommandPacket('HOME')
        
        if self.cancelled: return
        memory, objects = self.run_M_L()
        
        if self.cancelled: return
        
        if HPexSettingsTools.load_settings()['reset_directory_on_disconnect']:
            pathfile = self.get_hp_path()
        else:
            pathfile = None
            
        print(memory, objects)


        if not self.cancelled:
            wx.CallAfter(
                pub.sendMessage,
                f'xmodem.connectdone.{self.ptopic}',
                mem=int(memory),
                pathfile=pathfile,
                varlist=objects)

    def disconnect_from_server(self, pathfile):
        import wx
        if self.cancelled: return
        # Restore original directory if desired, and send command 'Q'
        # to quit server on calculator.
        try:
            if HPexSettingsTools.load_settings()['reset_directory_on_disconnect']:
                print('reset directory')
                if self.cancelled:
                    print('cancelled')
                    return

                pathfile.seek(0)
                print(pathfile.read())
                pathfile.seek(0)
                self.clear_extra_bytes()
                self.ser.flush()
                self.sendCommand(b'P')
                self.sendCommandPacket("$$$p")
                self.modem = HPXModem(self.ser)
                self.success = self.modem.send(pathfile, retry=4)
                
                if self.cancelled:
                    print('cancelled')
                    self.modem.abort()
                    # if we cancel at or beyond this point, the file
                    # has probably already been sent. we should delete
                    # it as a result.
                    # TODO: actually test this on real hardware
                    print('deleting $$$p')
                    self.clear_extra_bytes()
                    self.sendCommand(b'E')
                    self.sendCommandPacket("'$$$p' PURGE")
                    print('$$$p deleted')

                    return
                
                self.clear_extra_bytes()

                if self.cancelled:
                    self.modem.abort()
                    return
                
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
        print(total_packets, success_count, error_count)
        if self.use_callafter:
            import wx
        print(total_packets, success_count, error_count)
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
        self.modem.abort()
        # cancel any current server operation
        self.cancelled = True
        if self.use_callafter:
            import wx
            wx.CallAfter(
                pub.sendMessage,
                f'xmodem.cancelled.{self.ptopic}')
                           
        else:
            pub.sendMessage(
                f'xmodem.cancelled.{self.ptopic}')
