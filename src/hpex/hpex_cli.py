import threading
import sys
import os
import shutil
from pathlib import Path
import platform

_system = platform.system()
from pubsub import pub

from hpex.settings import HPexSettingsTools
if _system != 'Windows':
    from hpex.kermit_pubsub import KermitConnector
from hpex.xmodem_pubsub import XModemConnector
from hpex.xmodem_xsend_pubsub import XModemXSendConnector
from hpex.helpers import FileTools, KermitProcessTools, XModemProcessTools

class HPexCLI:
    def __init__(self, args):
        self.command = args.command[0]
        if self.command not in ['ksend', 'kget', 'xsend', 'xsrv_send', 'xsrv_get']:
            print('Error: invalid command.')
            return
        
        # if the file doesn't exist (or is a directory), don't even try.
        self.filename = Path(args.input_file[0])
        self.current_path = Path(os.getcwd())
        if _system != 'Windows':
            if 'get' not in self.command:
                if self.filename.is_dir():
                    print('Error: specified path is a directory.')
                    sys.exit(21) # EISDIR
                elif not self.filename.is_file():
                    print(f'Error: no such file: {self.filename}')
                    sys.exit(2) # ENOENT

        self.topic = 'HPexCLI'

        if _system == 'Windows':
            if self.command == 'ksend' or self.command == 'kget':
                print('Error: Kermit transfers not available on Windows.')
                sys.exit(1)
        # for info mode, just stop processing arguments if we get a
        # -i.
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
        pub.subscribe(self.xmodem_done, f'xmodem.done.{self.topic}')

        self.settings = HPexSettingsTools.load_settings()

        if args.finish:
            self.finish = True
        else:
            self.finish = False

        if args.baud:
            self.baud = args.baud
        else:
            # load the port specified in the settings
            self.baud = self.settings['baud_rate']

        # If we aren't transferring to a server, the flag to finish
        # will be ignored if passed. However, we still inform the user
        # about it.
        if self.command == 'xsend':
            if self.finish:
                print("Warning: ignoring option '-f' (finish remote server) specified in XSEND mode.")
        elif self.command == 'xsend' or self.command == 'xsrv_send' or self.command == 'ksend':
            print("Warning: ignoring option '-o' (overwrite on local) specified with send command")

        if args.overwrite:
            self.overwrite = True
            print('Overwriting file (if present) on local side.')
        else:
            self.overwrite = False
            
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
            print(f'Using autodiscovered port {self.port}.', end='')

            # separate the port declaration from other messages
            print()
        # this keeps track of whether we've already printed 100% to
        # the progress bar. if we have, we don't do it again, so that
        # the progress bar stays just one line.
        self.already_wrote_100 = False

        options = HPexSettingsTools.load_settings()

        options['baud_rate'] = self.baud

        print('If you cancel with ^C, you may have to press [CANCEL] or [ATTN] on the calculator.')
        if 'k' in self.command:
            if self.command == 'ksend':
                cmd = f'send {self.filename}'
                # print the warning we show in File[Get|Send]Dialog
            elif self.command == 'kget':
                cmd = ''
                if args.overwrite:
                    cmd += 'set file collision overwrite,'
                cmd += f'get {self.filename}'
                    
            if self.finish:
                cmd += ',finish'

            self.connector = KermitConnector()
            self.kermit = threading.Thread(
                target=self.connector.run,
                args=(self.port, self, cmd,
                      self.topic, True, False, options))
            
            self.kermit.start()
            
        elif self.command == 'xsrv_send':
            self.connector = XModemConnector()
            self.xmodem = threading.Thread(
                target=self.connector.run,
                args=(self.port,
                      self,
                      str(Path(self.filename).name),
                      'send_connect',
                      str(self.current_path),
                      self.topic,
                      False,
                      options))
            self.xmodem.start()
            
        elif self.command == 'xsrv_get':
            if self.overwrite:
                cmd = 'get_connect_overwrite'
            else:
                cmd = 'get_connect'
            self.connector = XModemConnector()
            self.xmodem = threading.Thread(
                target=self.connector.run,
                args=(self.port,
                      self,
                      str(Path(self.filename).name),
                      cmd,
                      str(self.current_path),
                      self.topic,
                      False,
                      options))
            self.xmodem.start()
            
        elif self.command == 'xsend':
            self.connector = XModemXSendConnector()
            self.xmodem = threading.Thread(
                target=self.connector.run,
                args=(self.port,
                      self,
                      self.filename,
                      self.topic,
                      False,
                      options))
            self.xmodem.start()
            print('Run XRECV now.')

    def kermit_newdata(self, data, cmd):
        # The 48 (I have no idea about the MK series) doesn't send any
        # information on progress when it sends a file over Kermit, we
        # disable this if we're receiving a file.
        
        if self.command == 'ksend':
            progress = KermitProcessTools.kermit_line_to_progress(data)
            if progress is not None and not self.already_wrote_100:
                # we have to subtract from the terminal width to make
                # everything fit
                self.print_progress_bar(progress)
                
            if progress == 100:
                self.already_wrote_100 = True

    def kermit_done(self, cmd, out):
        if self.command == 'kget':
            # If we don't print any status, there's no clear
            # indication that the transfer was successful.
            print('Complete!')

        sys.exit(1)

    def kermit_failed(self, cmd, out):
        # newlines separate the progress bar from the following
        # messages
        print()
        print('Kermit said:')
        print(out)
        print(f'\nKermit failed to transfer {self.filename} to {self.port}.')
        sys.exit(1)
        
    def xmodem_newdata(self, file_count, total,
                       success, error, should_update):
        # XModem doesn't need an already_wrote_100, because we have
        # should_update.
        if should_update:
            progress = XModemProcessTools.packet_count_to_progress(
                success, file_count)
           
            self.print_progress_bar(progress)

        
    # no data here either
    def xmodem_failed(self, cmd):
        print(f'\nXModem failed to transfer {self.filename} to {self.port}.')
        # have to exit because sometimes the done event is still sent
        sys.exit(1)
                
    def xmodem_done(self, file_count, total, success, error):
        # there is no progress in XModem receive, so we can't set the
        # progress to 100 to mark completion
        if self.command == 'xsrv_get':
            print('Complete!')
        else:
            # fill the bar the whole way (otherwise it stops at 99%)
            self.print_progress_bar(100)
            
        sys.exit(1)

    # from https://stackoverflow.com/a/34325723, but modified
    
    def print_progress_bar(self, iteration):
        # refetch the terminal size in case it's resized
        self.termcols = shutil.get_terminal_size()[0]
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
