import pickle
from pathlib import Path
import os

# TODO: should probably end up being a sequential version number (as
# opposed to semantic), and an application global of some kind
current_hpex_version = 1

# Although it is less OO, we use a dict to store settings instead of a
# dataclass. This has two advantages:
# - it allows us to easily contain a version number, which lets
#   a version transition seamlessly copy old settings over
# - it also makes it easier to add new settings (though the
#   dataclass module would also let this happen, it doesn't
#   have any versioning)

class HPexSettingsTools:
    @staticmethod
    def load_settings():
        # needed to help Python find the file
        p = Path('~/.hpexrc').expanduser()
        if not p.is_file():
            print('making new .hpexrc')
            # make new file with the defaults
            d = HPexSettingsTools.create_settings_dict()
            f = p.open('wb')
            pickle.dump(d, f)
            f.close()

            return d

        #print('is_file')
        f = p.open('rb')
        # if the current version number is greater than the version number in the file, 
        d = pickle.load(f)
        if d['version'] < current_hpex_version:
            # now we need to upgrade. this iterates over every entry
            # in the new dictionary and checks if a value for it
            # exists in the old dict. if so, it writes it to the new
            # dict, and otherwise, it keeps that key at the default value.
            print('updating version, old is', d['version'], 'new is', current_hpex_version)
            d_keys = d.keys()
            new_d = HPexSettingsTools.create_settings_dict()
            for key in new_d:
                print('key', key, 'found ', end='')
                if key in d_keys:
                    print('true')
                    new_d[key] = d[key]
                else:
                    print('false')

            # set version key to current version, it will have been
            # overwritten by the loop above
            new_d['version'] = current_hpex_version
            # now we need to save that to the file
            f.close()
            
            f = p.open('wb')
            pickle.dump(new_d, f)
            f.close()

            # and return the new improved dict
            return new_d

        # finally, otherwise just return the dict we read before
        f.close()
        return d
    
    """Create a new settings dictionary with default values and return it."""
    @staticmethod
    def create_settings_dict() -> dict:
        return {
            'version': current_hpex_version,
            'startup_dir': '~', # TODO: should probably be a Path
            'kermit_executable': 'ckermit',
            'baud_rate': '9600',
            'file_mode': 'Auto',
            'parity': '0 (None)',
            'kermit_cksum': '3',
            'disable_pty_search': False,
            'disconnect_on_close': False,
            'reset_directory_on_disconnect': True,
            'ask_for_overwrite': True,
            'start_in_xmodem': False
        }

