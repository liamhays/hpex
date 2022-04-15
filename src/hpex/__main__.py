import sys
import platform
import logging

_system = platform.system()

class HPex(object):
    # This is the main dispatcher class for all of HPex's
    # operations. It checks for arguments, and if it finds them, it
    # parses them and sends them to HPexCLI. Without arguments, it
    # calls HPexGUI and runs from there.
    def __init__(self):
        # Disable logging from the xmodem package.
        logging.disable()
        if len(sys.argv) > 1:
            # import argparse later and only if needed
            import argparse
            desc = \
            """Transfer file to calculator. If a serial port is not specified, HPex will try to find one automatically.

Commands:
ksend       send FILE to Kermit server
kget        get FILE from Kermit server and place in current directory
xsend       send FILE to XRECV on calculator
xsrv_send   send FILE to XModem server
xsrv_get    get FILE from XModem server"""
            
            # RawHelpTextFormatter https://stackoverflow.com/a/3853776
            parser = argparse.ArgumentParser(description=desc, formatter_class=argparse.RawTextHelpFormatter)

            if _system == 'Windows':
                parser.add_argument('command', metavar='COMMAND', nargs=1, help="Task to run, one of 'xsend', 'xsrv_send', or 'xsrv_get'.")
            else:
                parser.add_argument('command', metavar='COMMAND', nargs=1, help="Task to run, one of 'ksend', 'kget', 'xsend', 'xsrv_send', or 'xsrv_get'.")

            
            parser.add_argument(
                'input_file', metavar='FILE',
                nargs=1, help='File to send or receive')

            parser.add_argument(
                '-p', '--port', help='Serial port to connect to')
            
            parser.add_argument(
                '-b', '--baud',
                help='Baud rate for port (default 9600)')

            parser.add_argument(
                '-i', '--info',
                action='store_true',
                help='Run HP object info check on FILE instead of sending it')

            parser.add_argument(
                '-f', '--finish',
                action='store_true',
                help='End remote Kermit or XModem server after sending or receiving file')
            
            parser.add_argument(
                '-o', '--overwrite',
                action='store_true',
                help='Overwrite file if it already exists on local side')
            
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
    

