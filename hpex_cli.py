import threading
import sys
import shutil
from pathlib import Path

from pubsub import pub

from settings import HPexSettingsTools

from kermit_pubsub import KermitConnector
from xmodem_pubsub import XModemConnector
from helpers import FileTools, KermitProcessTools, XModemProcessTools

class HPexCLI:
    def __init__(self, args):
        print('__init__')
        #print(args)
#        print(sys.modules.keys())
        # if the file doesn't exist (or is a directory), don't even try.
        self.filename = Path(args.input_file[0])
        if not args.get:
            if self.filename.is_dir():
                print("Error: specified file is directory, which can't be sent.")
                sys.exit(1)
            elif not self.filename.is_file():
                print(f'Error: no such file: {self.filename}')
                sys.exit(1)
        self.topic = 'HPexCLI'

        # something similar goes for info mode: just stop processing
        # arguments if we get a -i.
        if args.info:
            print(FileTools.create_local_message(
                self.filename, self.filename.name))
            return
        
        # get terminal size
        self.termcols = shutil.get_terminal_size()[0]
        pub.subscribe(
            self.kermit_newdata, f'kermit.newdata.{self.topic}')
        pub.subscribe(
            self.kermit_failed, f'kermit.failed.{self.topic}')
        # we never have to cancel Kermit or XModem, because ^C kills
        # both of them just fine.

        pub.subscribe(self.kermit_done, f'kermit.done.{self.topic}')


        pub.subscribe(
            self.xmodem_newdata, f'xmodem.newdata.{self.topic}')
        pub.subscribe(
            self.xmodem_failed, f'xmodem.failed.{self.topic}')
        pub.subscribe(
            self.serial_port_error,
            f'xmodem.serial_port_error.{self.topic}')

        pub.subscribe(self.xmodem_done, f'xmodem.done.{self.topic}')

        self.settings = HPexSettingsTools.load_settings()
        
        if args.finish:
            self.finish = True
        else:
            self.finish = False
        #print(args.finish)
            
        if args.port:
            #print('port:', args.port)
            self.port = args.port
        else:
            # otherwise, find the port ourselves.
            self.port = FileTools.get_serial_ports(None)
            # no port found, normally from disabling a pty search
            if self.port == '':
                print("Error: could not autodiscover serial port. Enable pty searching in the GUI (if disabled) or specify a port with '-p'.")
                sys.exit(1)
            print(f'Using autodiscovered port {self.port}.')
            # separate port declaration from other messages
            print()

        if args.baud:
            #print('baud:', args.baud)
            self.baud = args.baud
        else:
            # load the port specified in the settings
            self.baud = self.settings['baud_rate']
            
        if args.xmodem:
            # self.protocol is the one that gets displayed to the user
            self.protocol = 'XModem'
        else:
            self.protocol = 'Kermit'


        self.get = args.get
        
        if args.parity:
            if args.parity == '0':
                self.parity = '0 (None)'
            elif args.parity == '1':
                self.parity = '1 (Odd)'
            elif args.parity == '2':
                self.parity = '2 (Even)'
            elif args.parity == '3':
                self.parity = '3 (Mark)'
            elif args.parity == '4':
                self.parity = '4 (Space)'
            else:
                print(f"Error: Parity '{args.parity}' is not one of 0, 1, 2, 3, or 4. Please use a valid value.")
                sys.exit(1)
                # die
        else:
            self.parity = self.settings['parity']

        #print(self.parity)
        if args.cksum:
            if args.cksum not in ('1', '2', '3'):
                print(f"Error: Kermit block check value '{args.cksum}' is not of 1, 2, or 3. Please use a valid value.")
                sys.exit(1)
                
            self.cksum = args.cksum
        else:
            self.cksum = self.settings['kermit_cksum']

        if args.filemode:
            if args.filemode == 'auto':
                self.file_mode = 'Auto'
            elif args.filemode == 'binary':
                self.file_mode = 'Binary'
            elif args.filemode == 'ascii':
                self.file_mode = 'ASCII'
            else:
                print(f"Error: Kermit file mode '{args.filemode}' not valid. Please use a valid option.")
                sys.exit(1)
        else:
            self.file_mode = self.settings['file_mode']

        if args.asname:
            self.asname = args.asname[0]
        else:
            self.asname = None
        self.filename = args.input_file[0]

        # the user can specify a Kermit block check value in XModem
        # mode, but we should warn them that it won't do anything

        # we check using args.cksum because I think (though I don't
        # really know) it will be more reliable than checking
        # self.cksum.
        if args.cksum and self.protocol == 'XModem':
            print(f"Warning: ignoring custom Kermit block check '{args.cksum}' specified in XModem mode.")

        # the same applies to -d in XModem mode
        if self.finish and self.protocol == 'XModem':
            print("Warning: ignoring option '-d' (finish remote server) specified in XModem mode.")

        if self.get and self.protocol == 'XModem':
            # we make self.get False here so that the message printed
            # later is accurate
            self.get = False
            print("Warning: ignoring option '-g' (get file) specified in XModem mode.")

        if args.overwrite and self.protocol == 'XModem':
            print("Warning: ignoring option '-o' (overwrite on local side) specified in XModem mode.")
            
        # ...and, we do the same for Kermit file mode in XModem mode.
        if args.filemode and self.protocol == 'XModem':
            print("Warning: ignoring Kermit file mode '{args.filemode}' specified in XModem mode.")
            # print an extra newline to separate the warnings from the
            # other info
            print()


        # this keeps track of whether we've already printed 100% to
        # the progress bar. if we have, we don't do it again, so that
        # the progress bar stays just one line.
        self.already_wrote_100 = False

        #TODO: WHAT IS THIS
        options = HPexSettingsTools.load_settings()

        options['baud_rate'] = self.baud
        options['parity'] = self.parity
        options['file_mode'] = self.file_mode
        options['kermit_cksum'] = self.cksum

        if not self.get:
            print(f"Starting transfer of '{self.filename}' to {self.port} using {self.protocol}...")

        else:
            if args.overwrite:
                print(f"Starting transfer of and overwriting '{self.filename}' from '{self.port}' over {self.protocol}... (no progress available)")
            else:
                print(f"Starting transfer of '{self.filename}' from '{self.port}' over {self.protocol}... (no progress available)")
            
        if self.protocol == 'Kermit':
            # print the warning we show in File*Dialog
            print('If you cancel with ^C, you may have to press [CANCEL] or [ATTN] on the calculator.')
            cmd = ''
            if not self.get:
                cmd = 'send'
                
                if self.asname:
                    cmd += ' /as-name:' + self.asname

                cmd += f' {self.filename}'
                
            else:
                if args.overwrite:
                    cmd += 'set file collision overwrite,'
                cmd += f'get {self.filename}'

            if self.finish:
                cmd += ',finish'
            #print(cmd)
            self.connector = KermitConnector()
            self.kermit = threading.Thread(
                target=self.connector.run,
                args=(self.port, self, cmd,
                      self.topic, True, False, options))
            
            self.kermit.start()
        else:
            self.connector = XModemConnector()
            self.xmodem = threading.Thread(
                target=self.connector.run,
                args=(self.port, self, self.filename,
                      self.topic, False, options))
            self.xmodem.start()

    def kermit_newdata(self, data, cmd):
        # The 48 (I have no idea about the MK series) doesn't send any
        # information on progress when it sends a file over Kermit, we
        # disable this if we're receiving a file.
        if not self.get:
            progress = KermitProcessTools.kermit_line_to_progress(data)
            if progress is not None and not self.already_wrote_100:
                # we have to subtract from the terminal width to make
                # everything fit
                self.print_progress_bar(progress)
                
            if progress == 100:
                self.already_wrote_100 = True

    def kermit_done(self, cmd, out):
        print('Finished!')

    def kermit_failed(self, cmd, out):
        # newlines separate the progress bar from the following
        # messages
        print()
        print('Kermit said:')
        print(out)
        print(f'\nKermit failed to transfer {self.filename} to {self.port}. Are all the necessary settings correct?')

    def xmodem_newdata(self, file_count, total,
                       success, error, should_update):
        # XModem doesn't need an already_wrote_100, because we have
        # should_update.
        if should_update:
            progress = XModemProcessTools.packet_count_to_progress(
                success, file_count)
           
            self.print_progress_bar(progress)
                
            
            #print('new_xmodem_data')

    # no data here either
    def xmodem_failed(self):
        print(f'\nXModem failed to transfer {self.filename} to {self.port}. Are all the necessary settings correct?')

    # no data
    def serial_port_error(self):
        print(f"\nXModem wasn't able to access {self.port}. Is it present?")

    def xmodem_done(self, file_count, total, success, error):
        # fill the bar the whole way (otherwise it stops at 99%)
        self.print_progress_bar(100)
        print(f'\nXModem successfully transfered {self.filename} to {self.port}.')


    # from https://stackoverflow.com/a/34325723, but modified for my
    # specific needs
    
    def print_progress_bar(self, iteration):
        total = 100
        prefix = 'Progress:'
        suffix = 'complete'
        # subtract 12, this seems to make it work
        length = self.termcols - 12 - len(prefix) - len(suffix)
        fill = '#'

        
        percent = int(100 * (iteration / total))
        filled_length = int(length * iteration // total)
        dash_bar = fill * filled_length + '-' * (length - filled_length)
        print(f'\r{prefix} |{dash_bar}| {percent}% {suffix}', end='\r')
        # Print New Line on Complete
        if iteration == total: 
            print()



if __name__ == '__main__':
    print("Don't run this file directly, run hpex.py and pass command line arguments to that file.")
