from pathlib import Path
import serial

import typing
# TODO: implement 1K XModem
class HPXModem(object):
    def __init__(self, ser: serial.Serial):
        self.ser = ser
        self.crcarray = []
        for crc in range(16):
            for inp in range(16):
                self.crcarray.append((crc ^ inp) * 0x1081)
        self.packet_count = 1
        self.cancelled = False
        
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
        packet.append(0x01)
        packet.append(self.packet_count & 0xff)
        packet.append(0xff - (self.packet_count & 0xff))
        packet.extend(data)
        packet.append((hpcrc & 0xff00) >> 8)
        packet.append(hpcrc & 0xff)
        return packet

    def _write_packet(self, packet: bytearray):
        self.ser.write(packet)
        print(packet)

    def _send_packet(self, data: bytes, retry: int) -> bool:
        packet = self._gen_packet(data)
        self._write_packet(packet)
        
        blankcount = 0
        p = self.ser.read()
        while p != b'\x06': # ACK
            if self.cancelled: return False
            if blankcount == retry:
                return False
            
            if p == b'\x15': # NAK
                # this will not increment the packet number, which is
                # the correct way to resend.
                self._write_packet(packet)
                
            if p == b'':
                blankcount += 1
            p = self.ser.read()
            print(p)
            
        print('packet sent')
        self.packet_count += 1
        return True

    def send(self, read_file: typing.BinaryIO, retry=9, callback=None) -> bool:
        if self.cancelled: return False
        
        blankcount = 0
        while True:
            if blankcount == retry:
                return False
            
            try:
                p = self.ser.read()
            except Exception as e:
                print(e)
                return False
            
            if p == b'D':
                # calculator is requesting HP XModem transfer
                break
            
            elif p == b'':
                blankcount += 1
                
            if self.cancelled: return False
                
        total_packets = 0
        success_count = 0
        error_count = 0
        
        # use 128-byte packets
        try:
            data = read_file.read(128)
            print(f'data is {data}')
        except Exception as e:
            print('read from file', e)
            return False
            
        while data != b'':
            if self.cancelled: return False
            total_packets += 1

            if len(data) < 128:
                data += b'\x00' * (128 - len(data))

            try:
                packet_success = self._send_packet(data, retry)
            except Exception as e:
                print('_send_packet', e)
                return False
            
            if self.cancelled: return False
            
            if packet_success:
                error_count = 0
                success_count += 1
            else:
                if error_count == retry:
                    return False
                else:
                    error_count += 1

            if callable(callback):
                callback.__call__(total_packets, success_count, error_count)

            try:
                data = read_file.read(128)
                #print(f'data is {data}')
            except Exception as e:
                print('read from file', e)
                return False
            
        try:
            self.ser.write(b'\x04')
            read_file.close()
        except Exception as e:
            print('EOT + close', e)



    def abort(self, count=2):
        for _ in range(count):
            self.ser.write(b'\x18')
        self.cancelled = True
