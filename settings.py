import pickle
from pathlib import Path
import os

#import wx

class HPexSettingsTools:
    @staticmethod
    def load_settings():
        # needed to help Python find the file
        p = Path('~/.hpexrc').expanduser()
        if not p.is_file():
            print('making new .hpexrc')
            # make new file with the defaults
            s = HPexSettings()
            f = p.open('wb')
            pickle.dump(s, f)
            f.close()

            return s

        #print('is_file')
        f = p.open('rb')
        ob = pickle.load(f)
        f.close()
        return ob
    
    # we're going to leave the save functionality alone for now,
    # because only HPexSettings ever needs it.
class HPexSettings:
    def __init__(self, startup_dir='~',
                 kermit_executable='ckermit',
                 baud_rate='9600', file_mode='Auto',
                 parity='0 (None)', kermit_cksum='3',
                 disable_pty_search=False,
                 disconnect_on_close=False,
                 reset_directory_on_disconnect=True,
                 ask_for_overwrite=True):
        
        self.startup_dir = startup_dir
        self.kermit_executable = kermit_executable
        self.baud_rate = baud_rate
        self.file_mode = file_mode
        self.parity = parity
        self.kermit_cksum = kermit_cksum
        self.disable_pty_search = disable_pty_search
        self.disconnect_on_close = disconnect_on_close
        self.reset_directory_on_disconnect = reset_directory_on_disconnect
        self.ask_for_overwrite = ask_for_overwrite
    def __str__(self):
        return (
            'startup_dir: ' + str(self.startup_dir) +
            '  kermit_executable: ' + str(self.kermit_executable) +
            '  baud_rate: ' + str(self.baud_rate) +
            '  file_mode: ' + str(self.file_mode) +
            '  parity: ' + str(self.parity) +
            '  kermit_cksum: ' + str(self.kermit_cksum) +
            '  disable_pty_search: ' + str(self.disable_pty_search) +
            '  disconnect_on_close: ' + str(self.disconnect_on_close) +
            '  reset_directory_on_disconnect: ' + str(self.reset_directory_on_disconnect) +
            '  ask_for_overwrite' + str(self.ask_for_overwrite))
