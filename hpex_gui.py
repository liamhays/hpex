import threading

from pathlib import Path

import wx
from pubsub import pub

from helpers import FileTools, KermitProcessTools
from file_dialogs import FileGetDialog, FileSendDialog
from dialogs import KermitConnectingDialog, RemoteCommandDialog, KermitErrorDialog, ObjectInfoDialog
from kermit_pubsub import KermitConnector
from settings import HPexSettingsTools
from settings_frame import SettingsFrame

class HPexGUI(wx.Frame):
    # The calculator has to be in translate mode 3, the most
    # translation, for this tool to work. Otherwise, Python (or is it
    # wx? I can't tell exactly) will bomb out, complaining about
    # Unicode issues.
    def __init__(self, parent):
        # otherwise, continue onward
        wx.Frame.__init__(self, parent, title='HPex')

        self.connected = False
        self.xmodem_mode = False
        self.topic = 'HPex'
        # in this class, we are only using 'remote directory', so
        # there's no need to bind kermit.newdata. However, other
        # classes do need to know when Kermit has printed new data.

        pub.subscribe(self.kermit_failed, f'kermit.failed.{self.topic}')
        pub.subscribe(
            self.kermit_cancelled, f'kermit.cancelled.{self.topic}')
        pub.subscribe(self.kermit_done, f'kermit.done.{self.topic}')
        
        self.menubar = wx.MenuBar()
        self.file_menu = wx.Menu()
        self.local_menu = wx.Menu()
        self.hp_menu = wx.Menu()

        # I don't know if the macro tools will get anywhere.
        #self.macro_item = self.file_menu.Append(
        #    wx.ID_ANY, 'Macro builder...',
        #    'Open the macro builder to create a multi-file macro.')

        #self.macro_run_item = self.file_menu.Append(
        #    wx.ID_ANY, 'Macro runner...',
        #    'Run a previously created macro.')
        
        self.settings_item = self.file_menu.Append(
            # pretty much self-explanatory
            wx.ID_PREFERENCES, 'Settings...', '')
        
        self.Bind(
            wx.EVT_MENU, lambda e: SettingsFrame(self).go())
        
        self.run_ckfinder_item = self.local_menu.Append(
            wx.ID_ANY, 'Calculate checksum of object...',
            'Calculate the checksum and filesize, and find the ROM revision.')
        self.Bind(
            # lambda forces the creation of a new object
            wx.EVT_MENU, lambda e: ObjectInfoDialog(self).go(),
            self.run_ckfinder_item)
        
        self.run_hp_command_item = self.hp_menu.Append(
           wx.ID_ANY, 'Run remote command...',
           'Run command on the calculator')

        self.Bind(
           wx.EVT_MENU,
           lambda e: RemoteCommandDialog(
               self,
               self.serial_port_box.GetValue()).go(),
           self.run_hp_command_item)
        
        self.menubar.Append(self.file_menu, '&File')
        self.menubar.Append(self.local_menu, '&Local')
        self.menubar.Append(self.hp_menu, '&Remote')
        
        self.SetMenuBar(self.menubar)



        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.toolbar_panel = wx.Panel(self)
        self.toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.kermit_radiobutton = wx.RadioButton(
            self.toolbar_panel, wx.ID_ANY, 'Kermit')
        
        self.xmodem_radiobutton = wx.RadioButton(
            self.toolbar_panel, wx.ID_ANY, 'XModem')

        # This lets me force the GUI into XModem mode on startup
        # (probably should be a configurable option)
        
        #self.xmodem_radiobutton.SetValue(True)
        #self.kermit_radiobutton.SetValue(False)
        #self.xmodem_mode = True

        self.toolbar_sizer.Add(
            self.kermit_radiobutton, 1, wx.EXPAND | wx.ALL)
        self.toolbar_sizer.Add(
            self.xmodem_radiobutton, 1, wx.EXPAND | wx.ALL)

        # when you click a radiobutton, the UI changes a little.
        self.kermit_radiobutton.Bind(
            wx.EVT_RADIOBUTTON, self.set_kermit_ui_layout)
        
        self.xmodem_radiobutton.Bind(
            wx.EVT_RADIOBUTTON, self.set_xmodem_ui_layout)

        # this has TE_PROCESS_ENTER so that you can whack enter in the
        # box to connect, which is surprisingly useful
        self.serial_port_box = wx.TextCtrl(
            self.toolbar_panel, style=wx.TE_PROCESS_ENTER)
        self.serial_port_box.Bind(wx.EVT_TEXT_ENTER, self.connect_to_48)
        
        self.refresh_button = wx.Button(
            self.toolbar_panel, wx.ID_REFRESH, 'Refresh All')

        self.refresh_button.Bind(wx.EVT_BUTTON,
                                 self.refresh_button_callback)
        
        self.connect_button = wx.Button(
            self.toolbar_panel, wx.ID_ANY, 'Connect')
        
        self.connect_button.Bind(wx.EVT_BUTTON, self.connect_to_48)

        self.toolbar_sizer.Add(self.serial_port_box, 1, wx.EXPAND)
        self.toolbar_sizer.Add(self.refresh_button, 1, wx.EXPAND)
        self.toolbar_sizer.Add(self.connect_button, 1, wx.EXPAND)

        self.toolbar_panel.SetSizerAndFit(self.toolbar_sizer)

        self.filebox_panel = wx.Panel(self)
        self.filebox_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.local_sizer = wx.BoxSizer(wx.VERTICAL)
        self.hp_sizer = wx.BoxSizer(wx.VERTICAL)

        # self.current_local_path is maintained as a Path object. It
        # only becomes a string when it has to be used in something
        # that doesn't support Paths directly.
        self.current_local_path = Path(
            HPexSettingsTools.load_settings().startup_dir)
        self.local_dir = wx.StaticText(
            self.filebox_panel,
            wx.ID_ANY,
            str(FileTools.home_to_tilde(self.current_local_path)))

        self.local_dir_picker = wx.DirPickerCtrl(
            self.filebox_panel,
            wx.ID_ANY,
            str(self.current_local_path))
        
        self.local_updir = wx.Button(
            self.filebox_panel,
            wx.ID_ANY,
            'Up')

        self.local_dir_button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.local_dir_button_sizer.Add(
            self.local_dir_picker, 1, wx.EXPAND | wx.ALL)

        self.local_dir_button_sizer.Add(
            self.local_updir, 1, wx.EXPAND | wx.ALL)

        self.local_dir_picker.Bind(
            wx.EVT_DIRPICKER_CHANGED, self.dirpicker_changed)
        
        self.local_updir.Bind(wx.EVT_BUTTON, self.local_move_up)


        self.local_files = wx.ListCtrl(
            self.filebox_panel, wx.ID_ANY,
            style=wx.LC_REPORT | wx.LC_ICON | wx.LC_ALIGN_LEFT | wx.LC_SINGLE_SEL)

        self.local_files.InsertColumn(0, 'Name')
        
        self.local_files.Bind(wx.EVT_LIST_ITEM_ACTIVATED,
                              self.double_click_on_local_file)

        # build the image list, which has just folders and files.
        self.local_image_list = wx.ImageList(24, 24)
        
        self.local_image_list.Add(
            wx.ArtProvider.GetBitmap(
                wx.ART_FOLDER, wx.ART_TOOLBAR, (24, 24)))

        self.local_image_list.Add(
            wx.ArtProvider.GetBitmap(
                wx.ART_NORMAL_FILE, wx.ART_TOOLBAR, (24, 24)))
        
        self.local_files.SetImageList(
            self.local_image_list, wx.IMAGE_LIST_SMALL)
        
        self.local_sizer.Add(
            self.local_dir_button_sizer, 0, wx.EXPAND | wx.ALL)
        self.local_sizer.Add(self.local_dir, 0, wx.EXPAND | wx.ALL)
        self.local_sizer.Add(self.local_files, 1, wx.EXPAND | wx.ALL)
        
        
        self.hp_dir_label = wx.StaticText(
            self.filebox_panel,
            wx.ID_ANY,
            'Not connected')


        self.hp_files = wx.ListCtrl(
            self.filebox_panel, wx.ID_ANY,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL)

        self.hp_files.InsertColumn(0, 'Name')
        self.hp_files.InsertColumn(1, 'Size (bytes)')
        self.hp_files.InsertColumn(2, 'Type')
        self.hp_files.InsertColumn(3, 'Checksum')
        
        self.hp_files.Bind(wx.EVT_LIST_ITEM_ACTIVATED,
                           self.double_click_on_hp_file)

        self.hp_files.Bind(wx.EVT_LIST_KEY_DOWN,
                           self.hp_key)
        
        self.hp_home_button = wx.Button(
            self.filebox_panel,
            wx.ID_ANY,
            'HOME')
        
        self.hp_updir_button = wx.Button(
            self.filebox_panel,
            wx.ID_ANY,
            'Up')

        self.hp_home_button.Bind(wx.EVT_BUTTON, self.hp_home)
        self.hp_updir_button.Bind(wx.EVT_BUTTON, self.hp_updir)
        # make the sizers line up
        self.hp_home_button.SetMinSize(self.local_dir_picker.GetSize())
        self.hp_dir_button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.hp_dir_button_sizer.Add(
            self.hp_home_button, 1, wx.EXPAND | wx.ALL)
        
        self.hp_dir_button_sizer.Add(
            self.hp_updir_button, 1, wx.EXPAND | wx.ALL)

        self.local_updir.Bind(wx.EVT_BUTTON, self.local_move_up)


        self.hp_sizer.Add(
            self.hp_dir_button_sizer, 0, wx.EXPAND | wx.ALL)
        self.hp_sizer.Add(self.hp_dir_label, 0, wx.EXPAND | wx.ALL)
        self.hp_sizer.Add(self.hp_files, 1, wx.EXPAND | wx.ALL)

        self.filebox_sizer.Add(self.local_sizer, 1, wx.EXPAND | wx.ALL)
        self.filebox_sizer.Add(self.hp_sizer, 1, wx.EXPAND | wx.ALL)

        self.filebox_panel.SetSizerAndFit(self.filebox_sizer)
        
        self.main_sizer.Add(self.toolbar_panel, 0, wx.EXPAND)
        # we want to set the stretch on the fileboxes so they can
        # expand with the window
        self.main_sizer.Add(self.filebox_panel, 1, wx.EXPAND)
        
        self.SetSizerAndFit(self.main_sizer)

        # the statusbar is the most important part of the application:
        # it tells you what's going on.
        self.CreateStatusBar()

        #### all the widgets have been drawn, initialize some
        #### variables and get everything up to speed and the correct
        #### configuration.

        # this variable does double-duty: when it's True, we store the
        # current path to it, and then on finish, we use it to restore
        # the directory of the calculator. I suppose eventually this
        # feature should be configurable in Settings.
        self.firstpath = True

        # these four variables keep track of the selections and view
        # status of the local and remote lists
        
        # the selection variables keep track of the name of the entry
        # in the list. this means that I should probably add a handler
        # for when the name isn't there anymore.
        self.local_top_index = 0
        self.local_selection = None
        self.hp_top_index = 0
        self.hp_selection = None
        
        self.refresh_all_files()
        self.refresh_port()


        self.updating_remote_path = False

        # like I said, this should be configurable---either XModem or
        # Kermit on startup
        self.set_kermit_ui_layout(None)
        self.hp_home_button.Disable()
        self.hp_updir_button.Disable()
        self.hp_files.Disable()

        self.Bind(wx.EVT_CLOSE, self.close)
        self.Show(True)

    def dirpicker_changed(self, event):
        # When the local directory picker changes, update the path
        # (self.current_local_path is a Path object, because I like
        # pathlib) and refresh the files in the box beneath it.
        self.current_local_path = Path(self.local_dir_picker.GetPath())

        self.refresh_local_files()

    def local_move_up(self, event):
        self.current_local_path = Path(self.current_local_path).parent

        # We want to update the path as quickly as possible, because
        # the dirpicker will say "None" for a short while if we
        # don't. I'm not fully sure how this happens, but it can.
        self.local_dir_picker.SetPath(str(self.current_local_path))
        print('self.current_local_path', self.current_local_path)

        self.populate_local_files()

    def hp_home(self, event):
        # Why don't we check for connection here? Because the internal
        # state will disable this button if we aren't connected.

        # spawn a kermit thread
        self.kermit_connector = KermitConnector()
            
        self.kermit = threading.Thread(
            target=self.kermit_connector.run,
            args=(self.serial_port_box.GetValue(),
                  self,
                  'remote host HOME',
                  self.topic))
        
        self.kermit.start()

    def hp_updir(self, event):
        self.kermit_connector = KermitConnector()
            
        self.kermit = threading.Thread(
            target=self.kermit_connector.run,
            args=(self.serial_port_box.GetValue(),
                  self,
                  'remote host UPDIR',
                  self.topic))
        
        self.kermit.start()
        
    def disable_on_disconnect(self):
        # These two functions are pretty obvious. Clear and disable or
        # enable widgets and get the states of everything correct.
        self.hp_files.DeleteAllItems()
        self.hp_dir_label.SetLabelText('')
        self.hp_files.Disable()
        self.hp_home_button.Disable()
        self.hp_dir_label.Disable()
        self.hp_updir_button.Disable()

    def enable_on_connect(self):
        self.kermit_radiobutton.Disable()
        self.xmodem_radiobutton.Disable()
        self.serial_port_box.Disable()
        self.hp_home_button.Enable()
        self.hp_updir_button.Enable()
        self.hp_dir_label.Enable()
        self.hp_files.Enable()
        
    def set_xmodem_ui_layout(self, event):
        # A connection check isn't really necessary, but it's a good
        # idea anyway.
        if not self.connected:
            self.xmodem_mode = True
            self.hp_dir_label.SetLabelText(
                'No remote variables in XModem mode')
            # don't disable hp_dir_label, because it makes it hard to
            # read
            self.disable_on_disconnect()
            # disable the connect button, too, so that the image put
            # forward matches the text in hp_dir_label
            self.connect_button.Disable()

    def set_kermit_ui_layout(self, event):
        self.xmodem_mode = False
        self.hp_dir_label.SetLabelText('')
        self.hp_files.DeleteAllItems()
        self.hp_files.Disable()
        self.hp_dir_label.Enable()
        self.connect_button.Enable()

        if not self.connected:
            self.hp_dir_label.SetLabelText('Not connected')

    def refresh_button_callback(self, event):
        # if we update the port while we're connected, we might get a
        # new port, which would keep Kermit from doing anything, and
        # put HPex into a blocking state.
        if not self.connected:
            self.refresh_port()
        self.refresh_all_files()
        
    def refresh_all_files(self, event=None):
        self.refresh_local_files()
        self.refresh_hp_files()

    def refresh_port(self, event=None):
        self.serial_port_box.SetValue(FileTools.get_serial_ports(self))

    def populate_local_files(self):
        # The way the file update functions change the statusbar is a
        # bit convoluted, though perfectly functional. They all start
        # by setting the statusbar correctly and doing their listctrl
        # mojo. Then, for the local side, we update the text and
        # dirpicker so that both ways of changing directories
        # (double-click in listctrl and dirpicker change) update the
        # widgets correctly.
        self.SetStatusText('Updating local files...')
        self.local_files.DeleteAllItems()
        # no hiddens (should be an option in settings)
        cdir_path = Path(self.current_local_path).expanduser().glob('*')

        cdir = []
        # convert Paths to strings
        for i in cdir_path:
            if not i.name.startswith('.'):
                cdir.append(str(i))
            
        cdir.sort()

        for i in cdir:
            if Path(i).expanduser().is_dir():
                # icon 0 is a folder
                icon = 0
            else:
                # icon 1 is a file
                icon = 1
                
                
            self.local_files.InsertItem(
                self.local_files.GetItemCount(),
                Path(i).name, icon)
                
        self.local_files.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        # put this here so that it will be called no matter how the
        # user chooses a new directory
        self.local_dir.SetLabelText(
            str(FileTools.home_to_tilde(self.current_local_path)))
        
        self.local_dir_picker.SetPath(
            str(self.current_local_path.expanduser()))

        # put this here so that it is always shown, even if we change
        # paths
        self.SetStatusText('Updated local files.')
        
    def refresh_local_files(self):
        # The difference between populate_local_files() and
        # refresh_local_files() is that refresh_local_files() stores
        # the selection (if present) and location in the
        # list. populate_local_files() just scans
        # self.current_local_dir and puts its contents into the
        # listctrl.
        
        # If we don't save where the user is in the listctrl, then on
        # a refresh, the list will go back to the top. That is
        # annoying and disorienting. However, this is a good way to
        # deal with it. Here's how it works: before we refresh, we
        # store where in the list the listctrl is centered (using the
        # top item) and, if there is a selection, we store that as
        # well. Then, we use populate_local_files() to clear and
        # redraw the listctrl, and write back the top item and
        # selection.

        self.local_top_index = self.local_files.GetTopItem()
        local_sel_index = self.local_files.GetFirstSelected()

        if local_sel_index >= 0: # something is selected
            # populate self.local_selection with the name of the
            # selected entry
            self.local_selection = self.local_files.GetItem(
                local_sel_index).GetText()
        else:
            self.local_selection = None
        # clear the local box, then reload it
        
        #print('top item', self.local_files.GetItem(local_top_index).GetText())
        self.populate_local_files()
        # this adjusts the position in the list so that the top item
        # from before is where it should be. The -1 makes the
        # adjustment correct, otherwise, the position in the list is
        # one item too low.
        loc = self.local_top_index + self.local_files.GetCountPerPage() - 1
        # prevent an assertionerror (more details in kermit_done)

        # however, it is important to note that the AssertionError
        # isn't a big deal, as it doesn't actually affect the
        # interface.

        # now, we write back the top item and selection
        if loc >= self.local_files.GetCountPerPage():
            print('loc', loc)
            self.local_files.EnsureVisible(loc)

        # check if there's a selection, like before. if there isn't
        # one, we just won't select anything.
        if self.local_selection:
            found_item_index = self.local_files.FindItem(
                0, self.local_selection)

            if found_item_index != -1: # item was found
                #print(self.local_files.GetItem(found_item_index))
                # find the item and make the listctrl select it.
                self.local_files.Select(found_item_index)

        # We don't tell the user (through the statusbar) that we
        # finished updating the local files /here/, because
        # populate_local files /always/ gets called. This one doesn't
        # always get called.


    def refresh_hp_files(self):
        if self.connected:
            # same thing here as in the local update...
            self.hp_top_index = self.hp_files.GetTopItem()
            hp_sel_index = self.hp_files.GetFirstSelected()
            
            if hp_sel_index >= 0:
                self.hp_selection = self.hp_files.GetItem(
                    hp_sel_index).GetText()
            else:
                self.hp_selection = None

            # ...except now we spawn Kermit to do the directory
            # scanning for us.
            self.SetStatusText('Updating remote variables...')
            self.kermit_connector = KermitConnector()
            
            self.kermit = threading.Thread(
                target=self.kermit_connector.run,
                args=(self.serial_port_box.GetValue(),
                      self,
                      'remote directory',
                      self.topic,
                      False))
            
            self.kermit.start()

    def double_click_on_hp_file(self, event):
        # Double-clicking (or pressing Enter, or Space) selects the
        # item, which brings up the FileGetDialog, allowing you to
        # copy the file.
        sel_index = self.hp_files.GetFirstSelected()
        # can't use the selection directly, because it has the colon
        # notation
        filename = self.hpvars[sel_index]

        checksum_hex = KermitProcessTools.checksum_to_hexstr(self.hpcrcs[sel_index])
        
        message = f"You have chosen to transfer '{filename}' from the HP48 at " + self.serial_port_box.GetValue() + '.'

        filestats = f'Size: {self.hpsizes[sel_index]}\nType: {self.hptypes[sel_index]}\nChecksum: {checksum_hex}'
        # we don't assign this to a variable, so that a new dialog
        # gets created every time.
        FileGetDialog(
            self, f'Get {filename}', message, filestats,
            self.serial_port_box.GetValue(), filename,
            self.current_local_path, self.refresh_all_files)
        

    def double_click_on_local_file(self, event):
        # Double-clicking a local file is very similar to
        # double-clicking a remote file, albeit with a few more
        # options and usable progress.
        filename = Path(
            self.current_local_path,
            self.local_files.GetItemText(
                self.local_files.GetFirstSelected()))

        # If it's a directory, switch and exit
        if filename.expanduser().is_dir():
            print(f'{filename} is a directory')

            self.current_local_path = filename
            print(self.current_local_path)
            self.local_dir_picker.SetPath(str(self.current_local_path))
            # populate, not refresh, because refresh has the selection
            # magic
            self.populate_local_files()
        
        else:
            # if self.hpvars is not defined yet, this will go
            # wrong. However, it shouldn't be possible, because in the
            # long run, I intend to make it impossible for the user to
            # open this dialog if the calculator isn't connected.
            if not hasattr(self, 'hpvars'):
                print('self.hpvars not defined yet')
                self.hpvars = []

            basename = Path(filename).name
            print(filename)
            message = FileTools.create_local_message(
                filename.expanduser(), basename)

            FileSendDialog(
                self,
                f"Send '{basename}'",
                f"You have chosen to send '{basename}'" +
                ' to the HP48 at ' + self.serial_port_box.GetValue() +
                '.',
                message,
                self.serial_port_box.GetValue(),
                # we have to give the dialog the full path so that
                # Kermit can get it
                filename.expanduser(),
                self.hpvars,
                self.xmodem_mode,
                self.refresh_all_files)

    def hp_key(self, event):
        # tab, delete, and backspace, because they're easy to reach,
        # all change directory
        k = event.GetKeyCode()
        if k in (wx.WXK_TAB, wx.WXK_DELETE, wx.WXK_BACK):
            self.updating_remote_path = True # set to false later
            
            sel_index = event.GetItem().GetId()
            dirname = self.hpvars[sel_index]
            if self.hptypes[sel_index] == 'Directory':
                self.SetStatusText(
                    f"Changing calculator directory to '{dirname}'")
                
                # it is a directory, so we'll change paths
                self.kermit_connector = KermitConnector()
                
                self.kermit = threading.Thread(
                    target=self.kermit_connector.run,
                    args=(self.serial_port_box.GetValue(),
                          self,
                          f"remote host '{dirname}' EVAL",
                          self.topic,
                          False))
                
                self.kermit.start()

            else:
                self.SetStatusText(f"'{dirname}' is not a directory.")
                
    def update_internal_kermit_data(self, output):
        # This is one of the most important functions in this entire
        # program. It takes the output from Kermit, runs it through
        # process_kermit_vars, which splits by lines and returns each
        # row (removing the one with the path and memory free in Port
        # 0), and then splits each row by columns and returns it.

        
        kermit_vars = KermitProcessTools.process_kermit_vars(output)
        # Column 1 is variable names.
        self.hpvars = [col[0] for col in kermit_vars]
        # Column 2 is variable sizes.
        self.hpsizes = [col[1] for col in kermit_vars]
        # Column 3 is variable types, but we populate this
        # differently. This iterates over each item in column 2,
        # replacing the contractions with the correct text (see below
        # in kermit_done), and building the list.
        self.hptypes = []
        for item in [col[2] for col in kermit_vars]:
            if item == 'RealNumber':
                self.hptypes.append('Real Number')
            elif item == 'GlobalName':
                self.hptypes.append('Global Name')
            else:
                self.hptypes.append(item)
        # Column 3 is variable checksums
        self.hpcrcs = [col[3] for col in kermit_vars]
        
        # clear the listctrl for good measure
        self.hp_files.DeleteAllItems()

        for f in self.hpvars:
            # Insert the items into the listctrl (so maybe
            # 'update_internal_kermit_vars' isn't the best name?)
            idx = self.hpvars.index(f)
            t = self.hptypes[idx]
            s = self.hpsizes[idx]
            c = self.hpcrcs[idx]
            
            item_index = self.hp_files.InsertItem(idx, f)
            self.hp_files.SetItem(item_index, 1, s)
            self.hp_files.SetItem(item_index, 2, t)
            # convert the decimal checksums to hex strings (I suppose
            # eventually we should have a user option for the base
            # they want the checksum in).
            self.hp_files.SetItem(
                item_index, 3,
                KermitProcessTools.checksum_to_hexstr(c))

        self.hp_files.SetColumnWidth(0, wx.LIST_AUTOSIZE)

    def kermit_cancelled(self, cmd, out):
        # The only time you can cancel Kermit in this class is if you
        # pres 'Cancel' in the connecting dialog. This function mostly
        # just restores state after that.
        print('kermit cancelled in HPex')
        out = KermitProcessTools.strip_blank_lines(out)

        self.disable_on_disconnect()
        
        self.connect_button.SetLabel('Connect')
        self.connected = False
        self.SetStatusText(
            'Kermit connection to ' +
            self.serial_port_box.GetValue() + ' was cancelled.')

    def kermit_failed(self, cmd, out):
        # If Kermit failed, notify the user, correct various states,
        # and tell them what Kermit said (why it failed).
        print('kermit failed in HPex')
        if cmd == 'finish':
            self.SetStatusText("Couldn't finish Kermit server on " +
                               self.serial_port_box.GetValue()
                               + '.')
            
            print('kermit failed on finish')
            KermitErrorDialog(self, out).Show(True)
            return
            
        self.connecting_dialog.Close()
        self.connect_button.SetLabel('Connect') # just in case
        self.connected = False # also just in case
        self.SetStatusText(
            "Kermit couldn't reach " +
            self.serial_port_box.GetValue() + '.')

        # Kermit likes to add blank lines and other junk to the
        # output, so this just cleans those up.
        out = KermitProcessTools.strip_blank_lines(out)
        # do some stuff with Kermit's output and stderr
        KermitErrorDialog(self, out).Show(True)
        
    def kermit_done(self, cmd, out):
        # This function is very large and quite complicated. Read
        # through to figure out what everything does.
        print('kermit_done in HPex')

        # strip them here like kermit_failed
        out = KermitProcessTools.strip_blank_lines(out)

        #print('cmd:', cmd)
        #print('out:', out)

        # handle 'finish' separately, which is a special case
        if 'finish' in cmd:
            # restore various states, including the connect button,
            # too, so that the image put forward matches the text in
            # hp_dir_label
            self.disable_on_disconnect()

            self.kermit_radiobutton.Enable()
            self.xmodem_radiobutton.Enable()
            self.connect_button.Enable()
            self.serial_port_box.Enable()
            
            self.hp_dir_label.SetLabelText('Not connected')
            # connecting_dialog can also refer to the finishing dialog
            self.connecting_dialog.Close()
            # if it didn't work, make it so that there's a chance the
            # user could try again
            self.connected = False
            self.connect_button.SetLabelText('Connect')

            self.SetStatusText('Finished Kermit server on ' +
                               self.serial_port_box.GetValue() +
                               '.')

        
        else:#if 'finish' not in cmd:
            if cmd == 'remote directory': # we connected
                
                # Real Number is two words, which means it's hard for
                # Python to process the same way as others. We will
                # replace this back later, but for now, these are
                # pushed together into one word.

                # I think these are the only two-word types. Do any
                # new-to-the-HP49 objects have multiple words in their
                # types, as told to Kermit?
                out = out.replace('Real Number', 'RealNumber')
                out = out.replace('Global Name', 'GlobalName')
                

                out = KermitProcessTools.remove_kermit_warnings(
                    out.splitlines())
                
                #print(out)
                # read these again to be processed
                self.hp_dir, self.memfree = KermitProcessTools.process_kermit_header(out)
                # these happen regardless of whether we're connected
                # or not.
                self.update_internal_kermit_data(out)
                self.hp_dir_label.SetLabelText(
                    f'{self.hp_dir}  {self.memfree} bytes free')

                # special things if we're already connected, that
                # means the user did a refresh or changed remote
                # directory

                if self.connected:

                    # we adjust and update this here so, because
                    # that's where the new data comes in. We also have
                    # to only update this when we are connected,
                    # otherwise it's basically irrelevant
                    if not self.updating_remote_path:
                        loc = self.hp_top_index + self.hp_files.GetCountPerPage() - 1
                        # prevent an assertionerror when there is less
                        # than one pagefull of files on the remote side
                        if loc >= self.hp_files.GetCountPerPage():
                            self.hp_files.EnsureVisible(loc)
                            
                            # again, the same thing as before.
                            if self.hp_selection:
                                found_item_index = self.hp_files.FindItem(
                                    0, self.hp_selection)

                            if found_item_index != -1:
                                self.hp_files.Select(
                                    # I think it's safer to search in
                                    # the populated list, because it
                                    # knows what it has, just in case
                                    # something varies between
                                    # self.hpvars and the list's
                                    # entries.
                                    self.hp_files.FindItem(
                                        0, self.hp_selection))
                    else:
                        self.updating_remote_path = False
                    # /this/ is where we update the statusbar after a
                    # remote refresh
                    self.SetStatusText('Updated remote variables.')
                    # return, because we're already connected and
                    # there's nothing left to do.
                    return
                
                self.connecting_dialog.Close()

                self.connect_button.SetLabel('Disconnect')
                self.connected = True
                self.enable_on_connect()
                # don't disable connect_button here!
                self.SetStatusText(
                    'Connected to ' +
                    self.serial_port_box.GetValue() +
                    ' successfully.')
                # now, we can sort out Kermit's output and put it in
                # the list
                if self.firstpath:
                    self.firstpath = self.hp_dir

                
            elif 'remote host' in cmd:
                # We changed directories. However, in
                # RemoteCommandDialog, we ran the arbitrary command
                # issued by the user. Since we changed directories, we
                # need to update the remote variables now, and the
                # statusbar indicates this as such.
                

                self.SetStatusText('Updating remote variables...')
                # refresh the path by calling remote directory
                self.kermit_connector = KermitConnector()
            
                self.kermit = threading.Thread(
                    target=self.kermit_connector.run,
                    args=(self.serial_port_box.GetValue(),
                          self,
                          'remote directory',
                          self.topic,
                          False))
                
                self.kermit.start()
                
        
        
    def connect_to_48(self, event):
        # This function is responsible for both connecting and
        # disconnecting. If we're connected, we disconnect, and if
        # we're disconnected, we connect.
        if self.serial_port_box.GetValue() == '':
            print('empty serial port box')
            wx.MessageDialog(self, 'Serial port box is empty! Cannot reach calculator.',
                             caption='Serial error',
                             style=wx.OK | wx.CENTRE | wx.ICON_ERROR).ShowModal()
            return
        self.kermit_connector = KermitConnector()
        
        if not self.connected:
            self.SetStatusText('Connecting to HP48...')

            # this will show automatically
            self.connecting_dialog = KermitConnectingDialog(
                self, self.kill_kermit_external,
                'Make sure the calculator is in Kermit server mode and set to translate mode 3.',
                'Connecting...')
            
            self.kermit = threading.Thread(
                target=self.kermit_connector.run,
                args=(self.serial_port_box.GetValue(),
                      self,
                      'remote directory',
                      self.topic,
                      False))
            
        else:
            # the user can choose to reset the directory to the
            # starting directory (when we connected) on disconnect.
            cmd = ''
            if HPexSettingsTools.load_settings().reset_directory_on_disconnect:
                cmd += f'remote host {self.firstpath} EVAL,'
            self.connecting_dialog = KermitConnectingDialog(
                self, self.kill_kermit_external,
                'Finishing...',
                "Sending 'finish' to calculator...") 
            
            # the event handler will take care of any troubles from
            # this

            self.kermit = threading.Thread(
                target=self.kermit_connector.run,
                args=(self.serial_port_box.GetValue(),
                      self,
                      cmd + 'finish',
                      self.topic,
                      False))
            
        self.kermit.start()
        
    # tell the thread to kill kermit, then kill the thread, then
    # close the "connecting" frame

    # needs an event, because this gets called by a bound event
    def kill_kermit_external(self, event):
        self.kermit_connector.kill_kermit()
        self.connecting_dialog.Close()
        
            
    def close(self, event):
        if HPexSettingsTools.load_settings().disconnect_on_close and self.connected:
            # disconnect because we're now connected
            self.connect_to_48(None)
            
        # If Kermit fails here, HPex will stop for a short moment
        # until Kermit gives up. I don't think this is an issue.
        self.Destroy()

