import glob
import os
import platform

_system = platform.system()

import re
from pathlib import Path

if _system == 'Windows':
    import serial.tools.list_ports

from hpex.crc_calculator import HPCRCCalculator, HPCRCException
from hpex.settings import HPexSettingsTools

class KermitProcessTools:
    """
    This class provides several static methods for processing Kermit's
    output, like reading the header and contents of `remote
    directory`.

    """

    @staticmethod
    def remove_kermit_warnings(splitoutput):
        # this stays so I don't try to filter it
        # 'Press the X or E key to cancel' is suppressed
        # by 'set quiet on'
        #for line in splitoutput:
        #    # remove Kermit's 'warning'
        #    if 'Press the X or E key' in line:
        #        splitoutput.remove(line)#splitoutput[splitoutput.index(line)])

        # sometimes, Kermit will remove stale lock files
        for line in splitoutput:
            if 'Removing stale lock' in line:
                splitoutput.remove(line)

        final = ''
        for i in splitoutput:
            # make the last element not nothing (''), instead, the
            # last line of Kermit's output
            if i != splitoutput[-1]:
                final += i + '\n'
            else:
                final += i

        return final
    
    @staticmethod
    def process_kermit_header(remote_dir_output):
        """
        This function takes the output of `remote directory` and
        returns a list with the calculator's directory as a string 
        and the memory free in user memory.

        """
        
        lines = remote_dir_output.split('\n')

        #KermitProcessTools.remove_kermit_warnings(lines)
        
        first_line = lines[0]
        #print('first_line', first_line)
        #print('lines', lines)

        header, memfree = first_line.split('}')
        header = header + '}'

        return (header, memfree)


    @staticmethod
    def strip_blank_lines(dat):
        s = dat.splitlines()
        # no need anymore, with 'set quiet on' in Kermit
        #KermitProcessTools.remove_kermit_warnings(s)
        # from https://stackoverflow.com/a/1140966
        p = os.linesep.join([o for o in s if o])

        #print(p)
        return p


    @staticmethod
    def kermit_line_to_progress(dat):
        try:
            if '%' in dat:
                spl = dat.split()
                for l in spl:
                    if '%' in l:
                        return int(l.replace('%', ''))
        except ValueError:
            pass
        
    @staticmethod
    def checksum_to_hexstr(checksum):
        return '#' + str(hex(int(checksum))).replace('0x', '').upper() + 'h'

    

    
class XModemProcessTools:
    @staticmethod
    def packet_count_to_progress(s, fc):
        return int((s / fc) * 100)

    @staticmethod
    def bytes_to_utf8(s: bytes) -> str:
        """Convert s (a bytes object containing 8-bit ASCII HP names)
        to UTF-8.

        Equivalent Unicode symbols found by searching
        unicode-table.com for something that matched the HP 48G
        character browser, as well as the RPL character set page on
        Wikipedia.

        """

        # Note that some of these characters can't actually be used in
        # names. They're here just in case.

        # And yeah, I realized well into this that the HP 48 character
        # order is mostly the same (maybe even identical to the
        # UTF-8), but I think this is a better way.
        conversion_table = {
            0x7f: '▒', # shaded block
            0x80: '∡',
            0x81: '', # x with overbar
            0x82: '▽', 0x83: '√', 0x84: '∫', 0x85: 'Σ', 0x86: '▶', 0x87: 'π', 0x88: '∂', 0x89: '≤', 0x8a: '≥',
            0x8b: '≠', 0x8c: '𝛼', 0x8d: '→', 0x8e: '←', 0x8f: '↓', 0x90: '↑', 0x91: 'γ', 0x92: 'δ', 0x93: 'ε',
            0x94: 'η', 0x95: 'θ', 0x96: 'λ', 0x97: 'ρ', 0x98: 'σ', 0x99: 'τ', 0x9a: 'ω', 0x9b: 'Δ', 0x9c: 'Π',
            0x9d: 'Ω',
            0x9e: '■', # Black Square
            0x9f: '∞',
            0xa0: ' ', # non-breaking space (Latin-1 Supplement)
            0xa1: '¡', 0xa2: '¢', 0xa3: '£', 0xa4: '¤', # currency sign
            0xa5: '¥', 0xa6: '¦', # Broken Bar, best matches HP 48 symbol
            0xa7: '§', 0xa8: '¨', # Combining Diaeresis
            0xa9: '©', 0xaa: 'ª', # Feminine Ordinal Indicator
            0xab: '«', 0xac: '¬', # Not Sign
            0xad: '­', # Soft Hyphen
            0xae: '®', 0xaf: '¯', # Macron
            0xb0: '°', 0xb1: '±', 0xb2: '²', 0xb3: '³', 0xb4: '´', # Acute Accent
            0xb5: 'µ', 0xb6: '¶', 0xb7: '·', # Middle Dot
            0xb8: '¸', # Cedilla
            0xb9: '¹', 0xba: 'º', # Masculine Ordinal Indicator
            0xbb: '»', 0xbc: '¼', 0xbd: '½', 0xbe: '¾', 0xbf: '¿', 0xc0: 'À', 0xc1: 'Á', 0xc2: 'Â', 0xc3: 'Ã',
            0xc4: 'Ä', 0xc5: 'Å', 0xc6: 'Æ', 0xc7: 'Ç', 0xc8: 'È', 0xc9: 'É', 0xca: 'Ê', 0xcb: 'Ë', 0xcc: 'Ì',
            0xcd: 'Í', 0xce: 'Î', 0xcf: 'Ï', 0xd0: 'Ð', 0xd1: 'Ñ', 0xd2: 'Ò', 0xd3: 'Ó', 0xd4: 'Ô', 0xd5: 'Õ',
            0xd6: 'Ö', 0xd7: '×', 0xd8: 'Ø', 0xd9: 'Ù', 0xda: 'Ú', 0xdb: 'Û', 0xdc: 'Ü', 0xdd: 'Ý', 0xde: 'Þ',
            0xdf: 'ß', 0xe0: 'à', 0xe1: 'á', 0xe2: 'â', 0xe3: 'ã', 0xe4: 'ä', 0xe5: 'å', 0xe6: 'æ', 0xe7: 'ç',
            0xe8: 'è', 0xe9: 'é', 0xea: 'ê', 0xeb: 'ë', 0xec: 'ì', 0xed: 'í', 0xee: 'î', 0xef: 'ï', 0xf0: 'ð',
            0xf1: 'ñ', 0xf2: 'ò', 0xf3: 'ó', 0xf4: 'ô', 0xf5: 'õ', 0xf6: 'ö', 0xf7: '÷', 0xf8: 'ø', 0xf9: 'ù',
            0xfa: 'ú', 0xfb: 'û', 0xfc: 'ü', 0xfd: 'ý', 0xfe: 'þ', 0xff: 'ÿ'
        }
        final_name = ''
        for b in s:
            if b >= 0x7f:
                final_name += conversion_table[b]
            else:
                final_name += chr(b)

        return final_name
class FileTools:
    @staticmethod
    def home_to_tilde(p):
        """Replaces the user's home directory in p with a tilde for
        compactness.

        """
        return Path(str(p).replace(str(Path.home()), '~'))
    @staticmethod
    def read_hp_ascii(f):
        modes_to_text = {
            'D': 'Degrees',
            'R': 'Radians',
            'G': 'Grads',
            '.': 'Dot',
            ',': 'Comma'}

        try:
            # open() can't handle the binary contents of a binary
            # object, so if this fails, it means the file isn't ASCII.

            with open(f, 'r') as content:
                h = re.compile(
                    '%%HP: *T\([0123]\)A\([DRG]\)F\([.,]+\);')
                match = h.match(content.readline())
                
                if match:
                    l = match.group()
                    #print('got match, line is:', l)
                    translate_mode = l.split('T(')[1]
                    angle_mode = l.split('A(')[1]
                    fraction_mode = l.split('F(')[1]
                    # get just the first character, as the split returns
                    # lists with the second item containing the thing we
                    # want.
                    return (translate_mode[0],
                            modes_to_text[angle_mode[0]],
                            modes_to_text[fraction_mode[0]])
                
                content.close()
                return None
            
        except Exception:# as e:
            #print(e)
            return None

    # get the CRC and create a binary file message if applicable
    @staticmethod
    def get_crc(f):
        # okay, so some info on S/SX version
        # F. https://www.hpcalc.org/hp48/docs/misc/revf.txt says that
        # there are no F version SXes anywhere, and that F is from the
        # header on a PDL (Program Development Link) transfer
        # library. Therefore, F doesn't exist, and the most recent
        # version of the FAQ (4.62) actually has an incorrect
        # statement in section 3.7 about the "missing" versions.

        # ROMs A-J (excluding F, G, H, and I) are SX only, while
        # versions K-R are GX only, excluding Q. These excluded
        # versions were never released.
        rom_versions_to_machines = {
            'A': 'S/SX',
            'B': 'S/SX',
            'C': 'S/SX',
            'D': 'S/SX',
            'E': 'S/SX',
            
            'F': 'is this PDL?',
            'G': 'what?',
            'H': 'what?',
            'I': 'what?',
            
            'J': 'S/SX', # end of S/SX versions

            'K': 'G/GX',
            'L': 'G/GX',
            'M': 'G/GX',
            'N': 'G/GX',
            'O': 'G/GX',
            'P': 'G/GX',
            'R': 'G/G+/GX', # all G+ machines have R ROMs, according
                            # to the 48 FAQ.
            'X': 'any ROM'} # X is common; it means any version
            

        crc_results = []
        #print('f is', f)
        try:
            crc_results = HPCRCCalculator(f).calc()
            crc_results[1] = KermitProcessTools.checksum_to_hexstr(crc_results[1])
        except (HPCRCException, FileNotFoundError) as e:
            print(e)
            # it's quite unlikely we'll get here, but if we do, we
            # manage it anyway. create_local_message will figure it out.
            return None
            
        if crc_results[0] in rom_versions_to_machines:
            crc_results[0] += ' (' + rom_versions_to_machines[crc_results[0]] + ')'
        else:
            crc_results[0] += ' (Unknown)'

        # append ' bytes' so that it doesn't happen if the file can't
        # be CRCed
        #crc_results[2] = ' bytes'
        return crc_results

    @staticmethod
    def create_local_message(filename, basename):
        bin_file_stats = FileTools.get_crc(filename)
        ascii_header = FileTools.read_hp_ascii(filename)
        message = ''
        if bin_file_stats:
            message = f"'{basename}' is an HP binary object.\nROM Revision: {bin_file_stats[0]} \nChecksum: {bin_file_stats[1]}\nObject size: {bin_file_stats[2]}"
            
        elif ascii_header:
            message = f"'{basename}' is an HP ASCII object.\nTranslate mode: {ascii_header[0]}\nAngle mode: {ascii_header[1]}\nFraction mark: {ascii_header[2]}"
            
        else:
            message = f"'{basename}' is not an HP object.\nFile size: " + str(Path(filename).expanduser().stat().st_size) + ' bytes'

        return message




    @staticmethod
    def get_serial_ports(parent):
        """On Linux, this function tries to find ttyUSB serial ports (it
        returns the first sorted if any are found), and if it finds
        none, it then looks for any empty port slot in /dev/pts. This
        way, you can use x48 or your actual calculator, and change
        ports or scan for new ones at will.

        On Windows, it simply returns the first USB COM port found.
        """

        return '/dev/pts/3'
        if _system == 'Windows':
            if parent != None:
                parent.SetStatusText('Searching for COM ports...')
            # get COM ports
            for p in serial.tools.list_ports.comports():
                # All USB fields will be defined (not None) if the port is USB
                if p.vid != None: # USB Vendor ID
                    if parent != None:
                        parent.SetStatusText('Using ' + p.device)
                    return p.device
            return '' # nothing found
        
        # we can pass None in for the parent and it won't try to
        # update the statustext
        if parent != None:
            parent.SetStatusText('Searching for ttyUSB ports...')
        usbttys = glob.glob('/dev/ttyUSB*')
    
        # we can check for a variable's contents as boolean
        if usbttys != []:
            if parent != None:
                parent.SetStatusText('Using ' + usbttys[-1])
            return usbttys[-1]
        
        if parent != None:
            parent.SetStatusText(
                'No ttyUSB ports found, serial port box empty.')

        disable_pty_search = HPexSettingsTools.load_settings()['disable_pty_search']

        if disable_pty_search:
            # just return nothing, to finish off the else above
            # this is a bit of a hack, but it does work
            return ''
        
        #print('disable_pty_search')
        
        # no ttyUSBs found? notify the user, though they won't see
        # this message unless there's no numbered ptys.
        if parent != None:
            parent.SetStatusText(
                'No ttyUSB ports found...searching for x48 (ptys).')
        # I think that x48 will try to find the lowest pty that is
        # not occupied by a terminal. For example, if ptys 0, 1,
        # 3, 4, 5, and 6 are in use, then x48 will choose
        # /dev/pts/2.
        devptys = glob.glob('/dev/pts/[0-9]*')
        devptys.sort()
        devpty_numbers = [int(Path(p).name) for p in devptys]
            

        for i in range(len(devpty_numbers)):
            if i not in devpty_numbers:
                if parent != None:
                    parent.SetStatusText(
                        'Using ' + '/dev/pts/' + str(i) +
                        ', assuming x48 mode (start x48 now).')
                    return '/dev/pts/' + str(i)

        # otherwise, use one more than the highest pty
        pty = Path('/dev/pts', str(int(Path(devptys[-1]).name) + 1))
        # notify them again
        if parent != None:
            parent.SetStatusText(
                'Using ' + str(pty) +
                ', assuming x48 mode (start x48 now).')
            
        # if there are no empty slots, we'll just return the
        # greatest-numbered port plus one, which is probably what x48
        # will allocate.
        #print(devptys)
        return str(pty)
        
class StringTools(object):
    @staticmethod
    def trim_serial_port(port_str):
        return re.sub(r'\s+', '', port_str)


    
