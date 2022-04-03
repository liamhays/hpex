import struct
import sys

# This file is a translation of ckfinder.c, a modified version of TASC
# (version 2.52) from Joe Horn's Goodies Disk #7, by Jonathan
# T. Higa. That means the whole algorithm is his code, though the
# translation to Python is all Liam. More details in ckfinder.c, and
# you can find where I changed his code to calculate only the ROM
# revision, checksum, and length, in that file as well.


class HPCRCException(Exception):
    """Raised when the file is invalid or something happens in the bit
    pushing and popping."""
    pass

class HPCRCCalculator:

    """This class finds the ROM revision and calculates the checksum 
    and object size of the filename passed in as `object_file`."""

    def __init__(self, object_file):
        self.object_file = object_file

    def calc(self):
        f = open(self.object_file, 'rb')

        romrev_header = f.read(5)#f.read(7)
        # HP 50 uses HPHP49, as far as I can tell
        if romrev_header != b'HPHP4':
            raise HPCRCException('No HPHP4n-* header found')

        f.read(2) # read out the "8-" or "9-" or whatever
        
        romrev = f.read(1)

        # here we would return romrev as a string (not bytes)
        
        NONE, SIZE, ASCIC, ASCIX, DIR = 0, -1, -2, -3, -4
        state = NONE
        
        # buf is our byte buffer, read into, popped, and pushed.
        
        # bsize holds the buffer size, which shrinks and grows as we
        # push and pop from 'buf'.
        
        # pro just holds the prolog once it has been read.
        
        # crc holds the final CRC, which gets updated with every new
        # byte.
        
        # obj_len is the same as skip in ckfinder.c. However, 'skip'
        # is a /terrible/ name, as it implies that it is referring to
        # data that is going to be skipped over. 'obj_len' is more
        # accurate, as the variable dictates how long we're going to
        # be reading data.
        
        # nibs is a number that gets incremented every loop. even
        # though we're reading bytes, we loop using a count in nibbles
        # (we pop and push bits out of and into buf to separate
        # nibbles in the byte), so it works out.
        buf, buffer_size, pro, crc, obj_len, nibs = 0, 0, 0, 0, 0, 0

        # read the first byte before the loop
        byte = f.read(1)
        
        # the names for ASCIC and ASCIX are from
        # https://www.hpcalc.org/details/4576, it seems
        while byte:
            #time.sleep(.8)
            # convert the read byte to a C short
            # 'c' is the representation of the read byte as an integer
            c = struct.unpack('B', byte)[0]
            
            # according to TASC, this pushes the low bits (8 bits in
            # this case, because the B type in struct is 8 bits) of c
            # onto the high end of buf. This is the way that we are
            # able to read the object with the bytes in the correct
            # order.
            
            # bsize also gets incremented nbits.
            
            # this may need error handling
            buf, buffer_size, c = self.pushbitq(buf, buffer_size, 8, c)

            if not obj_len:
                if state == NONE:
                    if buffer_size >= 20:
                        # &ing the bytes with 0xfffff gets only the five
                        # right-most nibbles, for the prolog
                        pro = hex(buf & self.lowbits(20))
                        #print('got prolog:', pro)
                        obj_len = 5
                        #           DOARRY    DOLNKARRY DOCSTR
                        if pro in ('0x29e8', '0x2a0a', '0x2a2c',
                                   #DOHSTR    DOGROB     DOLIB
                                   '0x2a4e', '0x2b1e', '0x2b40',
                                   #DOBAK     DOEXT0    DOCODE
                                   '0x2b62', '0x2b88', '0x2dcc'):
                            state = SIZE
                            
                        #             DOIDNT    DOLAM     DOTAG
                        elif pro in ('0x2e48', '0x2e6d', '0x2afc'):
                            state = ASCIC
                            
                        #            DORRP
                        elif pro == '0x2a96':
                            state = DIR
                            obj_len = 8
                            
                        #            DOBINT
                        elif pro == '0x2911':
                            obj_len = 10
                            
                        #            DOREAL
                        elif pro == '0x2933':
                            obj_len = 21
                            
                        #            DOEREL
                        elif pro == '0x2955':
                            obj_len = 26
                            
                        #            DOCMP
                        elif pro == '0x2977':
                            obj_len = 37
                            
                        #            DOECMP
                        elif pro == '0x299d':
                            obj_len = 47
                            
                        #            DOCHAR
                        elif pro == '0x29bf':
                            obj_len = 7
                            
                        #            DOROMP
                        elif pro == '0x2e92':
                            obj_len = 11
                            
                elif state == SIZE and buffer_size >= 20:
                    # this is triggered by arrays (all types),
                    # strings, hex strings, grobs, libraries, backups,
                    # library data objects, and code objects. All of
                    # these objects have a five-nibble length field
                    # after the prolog, so we read it just like we
                    # read the prolog.
                    state = NONE
                    obj_len = buf & self.lowbits(20)
                    #print('state is now', state)
                    #print('In state SIZE, obj_len is', obj_len)
                    
                elif state == ASCIC and buffer_size >= 8:
                    # State ASCIC is triggered by a DOIDNT, a DOLAM,
                    # or a DOTAG. The size of DOIDNT and DOLAM types
                    # is 7 + 2 * (num_chars), but we already read the
                    # prolog, so it's actually 5 + 2 *
                    # (num_chars). (DOTAG is described below)
                    state = NONE
                    # buf & self.lowbits(8) gives the lowest two
                    # nibbles of buf, which is the character count of
                    # the object (which makes sense, because user IDs
                    # can only be up to 256 chars long).
                    
                    # Tagged objects are listed as 12 + 2 *
                    # (num_chars) + (object_size). However, since
                    # we're just reading to the end of the file, we
                    # can subtract the 5 nibbles for the DOTAG address
                    # /and/ the 5 nibbles for the SEMI at the end of
                    # the object, leaving us with the length below.
                    obj_len = 2 + 2 * (buf & self.lowbits(8))
                    
                elif state == ASCIX and buffer_size >= 8:
                    # ASCIX is 'extended ASCII', which consists of a
                    # two-nibble length field, the data, and an
                    # identical length field. This makes the total
                    # nibble count 2 + 2 (for the length counts) + 2 *
                    # (num_of_chars). num_of_chars is those two-nibble
                    # fields, so we can just AND it with lowbits(8) to
                    # get what we want.
                    state = NONE
                    obj_len = 4 + 2 * (buf & self.lowbits(8))
                    
                elif state == DIR and buffer_size >= 20:
                    # A directory is an annoyingly complex object. I
                    # actually can't figure out why we use twenty
                    # bits, it looks like (according to that document
                    # above) that we should only be using eight, or
                    # maybe 13.
                    state = ASCIX
                    obj_len = buf & self.lowbits(20)
                    
                    
            while obj_len and buffer_size >= 4:
                # we don't need the number of bits we put in (4)
                buf, buffer_size, _, c = self.popbitq(
                    buf, buffer_size, 4)
                crc = self.calc_crc(crc, c)
                
                obj_len -= 1
                nibs += 1
            
            byte = f.read(1)

        # must be a list to get edited later
        return [romrev.decode(sys.stdout.encoding),
                #    we add in the 4.5 + len(name) bytes
                crc, (nibs / 2) + 4.5 + len(f.name)]



    def calc_crc(self, crc, nibble):
        return (crc >> 4) ^ (((crc ^ nibble) & 0xF) * 0x1081)


    def pushbitq(self, inbuf, inbsize, innbits, inbits):
        """This function pushes the lowest `innbits` of `inbits` onto 
        the high end of `inbuf`. Think about it like this:
        
        We have a number, 0xab, and we want to push 0xdc. If we tell
        this function that we want to push 8 bits (two nibbles) from
        0xdc onto 0xab, by specifying 0xab as inbuf and 0xdc as
        inbits, we get 0xdcab.
        
        Because we don't have pass-by-reference in Python, this
        returns the modified `buffer`, modified `buffer_size`, and
        modified `bits`. We use `bits` as a modified version of the
        byte we read in from the file.

        """
        #print('buf, bsize, nbits, and bits before pushing: {:x} {:x} {:x} {:x}'.format(inbuf, inbsize, innbits, inbits))
        inbits &= self.lowbits(innbits)
        inbuf |= inbits << inbsize
        inbsize += innbits
        if inbsize > 64: # 64 is 8 (the equivalent of CHAR_BIT) * 1 byte
            raise HPCRCException('Bit buffer overflow in pushbitq')

        #print('buf, bsize, nbits, and bits after pushing: {:x} {:x} {:x} {:x}'.format(inbuf, inbsize, innbits, inbits))
        return (inbuf, inbsize, inbits)
    
    def popbitq(self, inbuf, inbsize, innbits):
        """This function is basically a direct opposite to `popbitq`. 
        It takes one fewer argument, because it's a pop, not a push. It
        pops the lowest `innbits` of `inbuf` and decrements `inbsize`
        accordingly. Then, it returns those popped bits and the other
        modified variables.

        """
        #print("before pop: buf, bsize, nbits: {:x} {:x} {:x}".format(inbuf, inbsize, innbits))
        popped_bits = inbuf & self.lowbits(innbits)
        inbuf >>= innbits
        inbsize -= innbits
        if inbsize < 0:
            # bit buffer underflow, raise an exception
            raise HPCRCException('Bit buffer underflow in popbitq')
        #print("after pop: buf, bsize, nbits, b: {:x} {:x} {:x} {:x}".format(inbuf, inbsize, innbits, popped_bits))
        return (inbuf, inbsize, innbits, popped_bits)
    
    def lowbits(self, n):
        return (1 << n) - 1
