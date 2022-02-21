import wx
from settings import * 

# This class has to be seperate so that we can control the loading of
# wx in the CLI.
class SettingsFrame(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title='HPex Settings')
        
        self.parent = parent

    def go(self):
        self.current_settings = HPexSettingsTools.load_settings()
        #print(self.current_settings)
        
        self.main_sizer = wx.GridBagSizer()

        self.main_sizer.Add(
            wx.StaticText(
                self, wx.ID_ANY, 'Startup directory:'),
            pos=(0, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL)

        self.startup_dir_chooser = wx.DirPickerCtrl(
            self, wx.ID_ANY, path=os.getcwd())

        self.startup_dir_chooser.SetPath(
            str(Path(self.current_settings.startup_dir).expanduser()))
        
        self.main_sizer.Add(
            self.startup_dir_chooser, pos=(0, 1))

        self.main_sizer.Add(
            wx.StaticText(
                self, wx.ID_ANY, 'Kermit name:'),
            pos=(1, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL)

        self.kermit_executable_box = wx.TextCtrl(self)
        self.main_sizer.Add(self.kermit_executable_box, pos=(1, 1))
        self.kermit_executable_box.SetValue(self.current_settings.kermit_executable)
        # while the 48 only supports the first four baud rates, the 49
        # supports 15360, and the 49g+ and 50g, over USB, are fixed at
        # 115200. While the 50g also supports other rates through the
        # serial port, I don't see any reason to include them.

        # of course, I could be wrong. I don't have any hardware to
        # test this, and I only have this information from playing
        # with Emu48 for Android and x49gp.
        self.baud_rate_choices = [
            '1200', '2400', '4800', '9600', '15360', '115200']
        self.baud_rate_choice = wx.Choice(
            self, wx.ID_ANY, choices=self.baud_rate_choices)
        
        self.baud_rate_choice.SetSelection(
            self.baud_rate_choices.index(
                self.current_settings.baud_rate))

        self.file_mode_choices = ['Auto', 'Binary', 'ASCII']
        self.file_mode_choice = wx.Choice(
            self, wx.ID_ANY, choices=self.file_mode_choices)
        
        self.file_mode_choice.SetSelection(
            self.file_mode_choices.index(
                self.current_settings.file_mode))

        self.parity_choices = [
            '0 (None)', '1 (Odd)', '2 (Even)', '3 (Mark)', '4 (Space)']
        
        self.parity_choice = wx.Choice(
            self, wx.ID_ANY, choices=self.parity_choices)

        self.parity_choice.SetSelection(
            self.parity_choices.index(
                self.current_settings.parity))

        self.kermit_cksum_choices = ['1', '2', '3']
        self.kermit_cksum_choice = wx.Choice(
            self, wx.ID_ANY, choices=self.kermit_cksum_choices)

        self.kermit_cksum_choice.SetSelection(
            self.kermit_cksum_choices.index(
                self.current_settings.kermit_cksum))
        
        self.pty_search_check = wx.CheckBox(
            self, wx.ID_ANY,
            'Disable pty search, look only for ttyUSB ports')

        self.pty_search_check.SetValue(
            self.current_settings.disable_pty_search)

        self.disconnect_on_close_check = wx.CheckBox(
            self, wx.ID_ANY,
            'Disconnect the calculator on close if connected')

        self.disconnect_on_close_check.SetValue(
            self.current_settings.disconnect_on_close)

        self.reset_on_disconnect_check = wx.CheckBox(
            self, wx.ID_ANY,
            'Reset calculator directory on disconnect')

        self.reset_on_disconnect_check.SetValue(
            self.current_settings.reset_directory_on_disconnect)

        self.ask_for_overwrite_check = wx.CheckBox(
            self, wx.ID_ANY,
            'Ask to or warn about overwriting')

        self.ask_for_overwrite_check.SetValue(
            self.current_settings.ask_for_overwrite)

        self.start_in_xmodem_check = wx.CheckBox(
            self, wx.ID_ANY,
            'Start HPex in XModem mode')

        self.ok_button = wx.Button(self, wx.ID_OK, 'OK')
        self.ok_button.Bind(wx.EVT_BUTTON, self.ok)
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, 'Cancel')
        self.cancel_button.Bind(wx.EVT_BUTTON, self.cancel)
        
        self.main_sizer.Add(
            wx.StaticText(
                self, wx.ID_ANY, 'Baud rate:'),
            pos=(2, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL)
        
        self.main_sizer.Add(self.baud_rate_choice, pos=(2, 1))

        self.main_sizer.Add(
            wx.StaticText(
                self, wx.ID_ANY, 'Parity:'),
            pos=(3, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL)
        
        self.main_sizer.Add(self.parity_choice, pos=(3, 1))
        
        self.main_sizer.Add(
            wx.StaticText(
                self, wx.ID_ANY, 'Kermit file mode:'),
            pos=(4, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL)
        
        self.main_sizer.Add(self.file_mode_choice, pos=(4, 1))

        
        self.main_sizer.Add(
            wx.StaticText(
                self, wx.ID_ANY, 'Kermit checksum mode:'),
            pos=(5, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL)

        self.main_sizer.Add(self.kermit_cksum_choice, pos=(5, 1))

        
        self.main_sizer.Add(
            self.pty_search_check, pos=(6, 0), span=(1, 2))

        self.main_sizer.Add(
            self.disconnect_on_close_check, pos=(7, 0), span=(1, 2))

        self.main_sizer.Add(
            self.reset_on_disconnect_check, pos=(8, 0), span=(1, 2))

        self.main_sizer.Add(
            self.ask_for_overwrite_check, pos=(9, 0), span=(1, 2))

        self.main_sizer.Add(
            self.start_in_xmodem_check, pos=(10, 0), span=(1, 2))
        
        self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.button_sizer.Add(self.ok_button, 1, flag=wx.EXPAND)
        self.button_sizer.Add(self.cancel_button, 1, flag=wx.EXPAND)

        self.main_sizer.Add(
            self.button_sizer, pos=(11, 0), span=(1, 2), flag=wx.EXPAND)
        self.SetSizerAndFit(self.main_sizer)
        self.Show(True)

    def ok(self, event):
        print('ok')
        # Nothing we can really do about these lines...
        self.current_settings.startup_dir = self.startup_dir_chooser.GetPath()
        self.current_settings.baud_rate = self.baud_rate_choices[self.baud_rate_choice.GetSelection()]
        self.current_settings.kermit_executable = self.kermit_executable_box.GetValue()
        self.current_settings.parity = self.parity_choices[self.parity_choice.GetSelection()]
        self.current_settings.file_mode = self.file_mode_choices[self.file_mode_choice.GetSelection()]
        self.current_settings.kermit_cksum = self.kermit_cksum_choices[self.kermit_cksum_choice.GetSelection()]
        self.current_settings.disable_pty_search = self.pty_search_check.GetValue()
        self.current_settings.disconnect_on_close = self.disconnect_on_close_check.GetValue()
        self.current_settings.reset_directory_on_disconnect = self.reset_on_disconnect_check.GetValue()
        self.current_settings.ask_for_overwrite = self.ask_for_overwrite_check.GetValue()
        self.current_settings.start_in_xmodem = self.start_in_xmodem_check.GetValue()
        print(self.current_settings)
        # I could just use the builtin open() here, but I want to keep
        # my file access consistent across the settings frame. Because
        # load_settings uses Path, this does too.
        pickle.dump(
            self.current_settings,
            Path('~/.hpexrc').expanduser().open('wb'))
        self.Close()
        
    def cancel(self, event):
        # do nothing and close
        self.Close()
        
    
