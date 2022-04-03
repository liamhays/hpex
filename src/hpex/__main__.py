import sys
import platform

_system = platform.system()

class HPex(object):
    # This is the main dispatcher class for all of HPex's
    # operations. It checks for arguments, and if it finds them, it
    # parses them and sends them to HPexCLI. Without arguments, it
    # calls HPexGUI and runs from there.
    def __init__(self):
        if len(sys.argv) > 1:
            # user passed command-line arguments, figure out what they
            # are

            # import argparse later, and only if needed, because we
            # want to make this as fast as possible to start from the
            # command line.
            import argparse
            # no Kermit on Windows, so string varies depending on OS
            if _system == 'Windows':
                desc = 'Transfer file to calculator using XModem. If a serial port is not specified, HPex will try to find one automatically.'
            else:
                desc = 'Transfer file to calculator, using XModem or Kermit (default Kermit). If a serial port is not specified, HPex will try to find one automatically.'
            parser = argparse.ArgumentParser(
                description=desc)
            
            parser.add_argument(
                'input_file', metavar='FILE',
                nargs=1, help='File to send or receive')

            parser.add_argument(
                '-p', '--port', help='Serial port to connect to')
            
            parser.add_argument(
                '-b', '--baud',
                help='Baud rate for port (default 9600)')

            parser.add_argument(
                '-r', '--parity',
                help='Parity to use: one of 0 (none, default), 1 (odd), 2 (even), 3 (mark), or 4 (space)')

            parser.add_argument(
                '-i', '--info',
                action='store_true',
                help='Run HP object info check on FILE instead of sending it')

            if _system != 'Windows':
                parser.add_argument(
                    '-x', '--xmodem',
                    action='store_true',
                    help="Use XModem instead of Kermit, only available for sending files")

                parser.add_argument(
                    '-d', '--finish',
                    action='store_true',
                help='Finish remote server after transfer in Kermit mode')

                parser.add_argument(
                    '-g', '--get',
                    action='store_true',
                    help='Get file (must be single name, no path) from server')
                
                parser.add_argument(
                    '-c', '--cksum',
                    help='Kermit block check: one of 1, 2, or 3 (default); applicable only in Kermit mode')

                parser.add_argument(
                    '-f', '--filemode',
                    help="Kermit file mode: one of 'auto', 'binary', or 'ascii'")
                
                parser.add_argument(
                    '-a', '--asname',
                    nargs=1, help='Name to rename file as on calculator, when sending with Kermit')

                parser.add_argument(
                    '-o', '--overwrite',
                    action='store_true',
                    help='Overwrite file on local side')
            
            from hpex.hpex_cli import HPexCLI
            #print(sys.modules.keys())
            HPexCLI(parser.parse_args())

        else:
            # otherwise, do GUI
            import wx
            app = wx.App(False)
            from hpex.hpex_gui import HPexGUI
            HPexGUI(None)
            app.MainLoop()


def run_as_main():
    HPex()

# No __name__ == '__main__' component makes this not work with 'python
# -m hpex', which is what we prefer anyway.
    

