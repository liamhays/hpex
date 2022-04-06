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

        return '/dev/pts/1'
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
