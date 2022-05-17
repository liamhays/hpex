from pathlib import Path
import serial
import time

import typing

class Ser(object):
    def __init__(self, ser):
        self.ser = ser
    def write(self, data):
        print('write', data)
        self.ser.write(data)
    def read(self):
        r = self.ser.read()
        print('read', r)
        return r
    
# TODO: implement 1K XModem
class HPXModem(object):
    def __init__(self, ser: serial.Serial):
        self.ser = Ser(ser)#ser
        self.crcarray = []
        for crc in range(16):
            for inp in range(16):
                self.crcarray.append((crc ^ inp) * 0x1081)
        self.packet_count = 1
        self.cancelled = False
        self.got_ack = False

    def _read_from_file(self) -> bytes:
        try:
            if self.bytes_remaining < 1024:
                data = read_file.read(128)
            else:
                data = read_file.read(1024)
            print(f'data is {data}')
        except Exception as e:
            print('read from file', e)
            return False

        self.bytes_remaining -= len(data)
        return data
    
    def _stringcrc(self, s: bytes) -> int:
        result = 0
        for i in s:
            k = (result & 0xf) << 4
            result = (result >> 4) ^ self.crcarray[k + (i & 0xf)]
            k = (result & 0xf) << 4
            result = (result >> 4) ^ self.crcarray[k + (i >> 4)]
        return result


    def _gen_packet(self, data: bytes) -> bytearray:
        hpcrc = self._stringcrc(data)
        packet = bytearray()
        if len(data) == 128:
            packet.append(0x01)
        elif len(data) == 1024:
            packet.append(0x02)
        # use self.success_count because if we hit an error,
        # self.total_packets will keep incrementing but success_count
        # won't (which is what we want).

        # have to add 1 though because self.success_count is 0-indexed
        packet.append((self.success_count+1) & 0xff)
        packet.append(0xff - ((self.success_count+1) & 0xff))
        packet.extend(data)
        packet.append((hpcrc & 0xff00) >> 8)
        packet.append(hpcrc & 0xff)
        return packet
    
    def _write_packet(self, packet: bytearray):
        self.ser.write(packet)
        print(packet)

    def _send_packet(self, data: bytes, retry: int) -> bool:
        self.got_ack = False

        packet = self._gen_packet(data)
        self._write_packet(packet)
        
        blankcount = 0
        p = self.ser.read()
        while p != b'\x06': # ACK
            if self.cancelled:
                print('self.cancelled in ACK loop')
                return False
            if blankcount == retry:
                return False
            
            if p == b'\x15': # NAK
                # this will not increment the packet number, which is
                # the correct way to resend.
                self._write_packet(packet)

            elif p == b'\x18': # CAN
                # If we get a CAN when we want ACK/NAK, we are supposed to cancel.
                return False
            
            elif p == b'':
                blankcount += 1

            if self.cancelled:
                print('self.cancelled in ACK loop')
                return False
            p = self.ser.read()
            print(p)

        if self.cancelled:
            time.sleep(.2)
            print('sending CAN 3 times')
            # If cancelled, we are supposed to send CAN multiple times
            # in place of SOH
            self.ser.write(b'\x18\x18\x18')
            print('self.cancelled in _send_packet')
            return False
        
        self.got_ack = True
        print('packet sent')
        self.total_packets += 1
        return True

    def send(self, read_file: typing.BinaryIO, retry=9, callback=None) -> bool:
        self.bytes_remaining = len(read_file.read())
        read_file.seek(0)
        
        if self.cancelled: return False
        
        blankcount = 0
        # read from serial until calculator sends b'D', which means
        # it's requesting an HP XModem transfer.
        while True:
            if blankcount == retry:
                return False
            
            try:
                p = self.ser.read()
            except Exception as e:
                print(e)
                return False
            
            if p == b'D':
                # start the transfer
                break
            
            elif p == b'':
                # if blank, the calculator might have failed. begin
                # counting.
                blankcount += 1
                
            if self.cancelled: return False

        
        self.total_packets = 0
        self.success_count = 0
        self.error_count = 0
        
        # We have to use 1024-byte packets as much as possible so that
        # cancelling actually works.

        data = self._read_from_file()
        while data != b'':
            print('self.cancelled', self.cancelled)
            #self.total_packets += 1

            if len(data) < 128:
                data += b'\x00' * (128 - len(data))

            try:
                packet_success = self._send_packet(data, retry)
            except Exception as e:
                print('_send_packet', e)
                return False

            if packet_success:
                self.error_count = 0
                self.success_count += 1
            else:
                print('packet failure')
                if self.cancelled:
                    return False
                if self.error_count == retry:
                    return False
                else:
                    self.error_count += 1

            if callable(callback):
                callback.__call__(self.total_packets, self.success_count, self.error_count)

            data = self._read_from_file()

        try:
            self.ser.write(b'\x04')
            read_file.close()
        except Exception as e:
            print('EOT + close', e)



    # Connectivity Kit sends 3 CANs

    # We have to get this right, because the XModem server (at least
    # on HP 48) likes to crash the whole calculator if this doesn't
    # work.
    def abort(self, count=3):
        #print(self.got_ack)
        #if not self.got_ack:
        #    p = self.ser.read()
        #    print(p)
        #    while p != b'\x06':
        #        p = self.ser.read()
        #        print(p)
        #    self.got_ack = True
            
        self.cancelled = True
        print('abort')

        #for _ in range(count):
        #    print('cancel')
        #    self.ser.write(b'\x18')
        #self.ser.close()
