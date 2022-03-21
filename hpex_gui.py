import threading

# global TODO: need some kind of "Kermit/XModem busy" indicator in main frame
# TODO: maybe probe IOPAR on connect to see if calculator is in mode 3---but might be too slow
from pathlib import Path
import os

import wx
from pubsub import pub

from helpers import FileTools, KermitProcessTools, StringTools
from file_dialogs import FileGetDialog, FileSendDialog
from dialogs import KermitConnectingDialog, RemoteCommandDialog, KermitErrorDialog, ObjectInfoDialog
from kermit_pubsub import KermitConnector
from settings import HPexSettingsTools
from settings_frame import SettingsFrame
from kermit_variable import KermitVariable

# These have to spawn a progress window and start the file transfer
class HPTextDropTarget(wx.TextDropTarget):
    def __init__(self, window):
        wx.TextDropTarget.__init__(self)
        self.window = window
        self.topic = 'HPex'
        
    def OnDropText(self, x, y, data):
        print('data is', data)
        wx.CallAfter(
            pub.sendMessage,
            f'ui.transfer_to_hp.{self.topic}',
            path=data)
        return True

# here, we have to transfer a KermitVariable object, so we extend
# wx.DropTarget
class LocalTextDropTarget(wx.TextDropTarget):
    def __init__(self, window):
        wx.TextDropTarget.__init__(self)
        self.window = window
        self.topic = 'HPex'
        
    def OnDropText(self, x, y, data):
        print('data in local text is', data)
        wx.CallAfter(
            pub.sendMessage,
            f'ui.transfer_to_local.{self.topic}',
            sel_index=data)
        return True


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
        
        # self.current_local_path is maintained as a Path object. It
        # only becomes a string when it has to be used in something
        # that doesn't support Paths directly.
        #self.current_local_path = Path('/home/liam/Dropbox/comp/hp/48/projects/cal/')
        #self.current_local_path = Path('/home/liam/tests/')
        self.current_local_path = Path(
            HPexSettingsTools.load_settings()['startup_dir'])
        
        # in this class, we are only using 'remote directory', so
        # there's no need to bind kermit.newdata. However, other
        # classes do need to know when Kermit has printed new data.

        pub.subscribe(self.kermit_failed, f'kermit.failed.{self.topic}')
        pub.subscribe(
            self.kermit_cancelled, f'kermit.cancelled.{self.topic}')
        pub.subscribe(self.kermit_done, f'kermit.done.{self.topic}')

        pub.subscribe(
            self.transfer_to_hp, f'ui.transfer_to_hp.{self.topic}')
        pub.subscribe(
            self.transfer_to_local, f'ui.transfer_to_local.{self.topic}')
        
        self.menubar = wx.MenuBar()
        self.file_menu = wx.Menu()
        self.hp_menu = wx.Menu()
        
        self.send_menuitem = self.file_menu.Append(
            wx.ID_ANY, '&Send selected local file\tCtrl+S', '')

        self.Bind(
            wx.EVT_MENU, self.send_menu_callback, self.send_menuitem)
        
        self.get_menuitem = self.file_menu.Append(
            wx.ID_ANY, '&Get selected remote file\tCtrl+G', '')

        self.Bind(
            wx.EVT_MENU, self.get_menu_callback, self.get_menuitem)

        self.file_menu.AppendSeparator()
                
        self.run_ckfinder_item = self.file_menu.Append(
            wx.ID_ANY, 'Calculate checksum of &object...\tCtrl+O',
            'Calculate information about HP object')
        
        self.Bind(
            # lambda forces the creation of a new object
            wx.EVT_MENU, lambda e: ObjectInfoDialog(self, self.current_local_path).go(),
            self.run_ckfinder_item)
        self.file_menu.AppendSeparator()

        self.settings_item = self.file_menu.Append(
            # pretty much self-explanatory
            wx.ID_PREFERENCES, 'Settings...\tCtrl+,', '')
        
        self.Bind(
            wx.EVT_MENU, lambda e: SettingsFrame(self).go(), self.settings_item)


        
        self.run_hp_command_item = self.hp_menu.Append(
            wx.ID_ANY, '&Run remote command...\tCtrl+R',
            'Run command on the calculator over Kermit')

        self.Bind(
            wx.EVT_MENU,
            self.start_remote_command_dialog,
            self.run_hp_command_item)
        
        self.menubar.Append(self.file_menu, '&File')
        self.menubar.Append(self.hp_menu, '&Remote')
        
        self.SetMenuBar(self.menubar)



        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.toolbar_panel = wx.Panel(self)
        self.toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.kermit_radiobutton = wx.RadioButton(
            self.toolbar_panel, wx.ID_ANY, 'Kermit')
        
        self.xmodem_radiobutton = wx.RadioButton(
            self.toolbar_panel, wx.ID_ANY, 'XModem')

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
        self.serial_port_box.Bind(wx.EVT_TEXT_ENTER, self.connect_callback)
        
        self.refresh_button = wx.Button(
            self.toolbar_panel, wx.ID_REFRESH, 'Refresh All')

        self.refresh_button.Bind(wx.EVT_BUTTON,
                                 self.refresh_button_callback)
        
        self.connect_button = wx.Button(
            self.toolbar_panel, wx.ID_ANY, 'Connect')
        
        self.connect_button.Bind(wx.EVT_BUTTON, self.connect_callback)

        self.toolbar_sizer.Add(self.serial_port_box, 1, wx.EXPAND)
        self.toolbar_sizer.Add(self.refresh_button, 1, wx.EXPAND)
        self.toolbar_sizer.Add(self.connect_button, 1, wx.EXPAND)

        self.toolbar_panel.SetSizerAndFit(self.toolbar_sizer)

        self.filebox_panel = wx.Panel(self)
        self.filebox_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.local_sizer = wx.BoxSizer(wx.VERTICAL)
        self.hp_sizer = wx.BoxSizer(wx.VERTICAL)

 
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

        self.local_files.Bind(
            wx.EVT_LIST_ITEM_ACTIVATED, self.local_item_activated)
        
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

        self.hp_files.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.hp_item_activated)
        
        #### Drag and Drop initialization
        # we need separate drop targets for both listctrls
        # also, a target widget must be active for drop to work.
        local_drop_target = LocalTextDropTarget(self.local_files)
        self.local_files.SetDropTarget(local_drop_target)
        hp_drop_target = HPTextDropTarget(self.hp_files)
        self.hp_files.SetDropTarget(hp_drop_target)
        
        self.local_files.Bind(wx.EVT_LIST_BEGIN_DRAG, self.local_file_drag)
        self.hp_files.Bind(wx.EVT_LIST_BEGIN_DRAG, self.hp_file_drag)

        
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


        self.CreateStatusBar()

        #### all the widgets have been drawn, so initialize some
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


        # this variable indicates when a Kermit 'remote directory' has
        # been issued but the actual remote path has not changed. This
        # occurs when the Refresh button is pressed.
        self.new_remote_path = False

        self.disable_on_disconnect()

        xmodem = HPexSettingsTools.load_settings()['start_in_xmodem']
        if xmodem:
            self.set_xmodem_ui_layout(event=None)
            # select the XModem radiobutton
            self.xmodem_radiobutton.SetValue(True)
            
        else:
            self.set_kermit_ui_layout(event=None)


        #self.hp_home_button.Disable()
        #self.hp_updir_button.Disable()
        #self.hp_files.Enable()

        # The default Frame size is just too small, so we make it
        # bigger.
        size = self.GetSize()
        size *= 1.5
        self.SetSize(size)

        
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
            args=(StringTools.trim_serial_port(self.serial_port_box.GetValue()),
                  self,
                  'remote host HOME',
                  self.topic))
        
        self.kermit.start()

    def hp_updir(self, event):
        self.SetStatusText(f'Running UPDIR on calculator...')
        self.kermit_connector = KermitConnector()
            
        self.kermit = threading.Thread(
            target=self.kermit_connector.run,
            args=(StringTools.trim_serial_port(self.serial_port_box.GetValue()),
                  self,
                  'remote host UPDIR',
                  self.topic))
        
        self.kermit.start()

    # restore the drop targets to both listboxes
    # this function is needed when a transfer fails
    def make_drop_targets(self):
        local_drop_target = LocalTextDropTarget(self.local_files)
        self.local_files.SetDropTarget(local_drop_target)
        hp_drop_target = HPTextDropTarget(self.hp_files)
        self.hp_files.SetDropTarget(hp_drop_target)
        
    def local_file_drag(self, event):
        # If we remove the drop target, you can't drop here, so the
        # interface seems more normal: you can only drop on the other
        # listctrl. The same thing is implemented in hp_file_drag.

        file_path = Path(
            self.current_local_path,
            self.local_files.GetItemText(
                self.local_files.GetFirstSelected()))

        # can't drag a directory!
        if os.path.isdir(file_path):
            print('is directory')
            return

        self.local_files.SetDropTarget(None)
        print('file_path is', file_path)

        # trigger the drop event
        data = wx.TextDataObject(str(file_path))
        drop_source = wx.DropSource(self.local_files)
        drop_source.SetData(data)
        drop_source.DoDragDrop(True)

        # we have to recreate the object every time (as opposed to
        # making one in __init__), otherwise we get an 'object
        # deleted' error.
        local_drop_target = LocalTextDropTarget(self.local_files)
        self.local_files.SetDropTarget(local_drop_target)
        
    def hp_file_drag(self, event):
        self.hp_files.SetDropTarget(None)
        sel_index = self.hp_files.GetFirstSelected()

        # I would like to make a DropTarget that uses some kind of
        # subclass of wx.DataObject which holds a KermitVariable, but
        # a) that's hard to implement, and b) I don't think we need to
        # carry around all that information all the time.
        ####
        # A much easier method is to transfer the selected item index,
        # since that isn't going to change. This also means that we
        # don't have to search based on variable name later on.
        data = wx.TextDataObject(str(sel_index))#varname)
        drop_source = wx.DropSource(self.hp_files)
        drop_source.SetData(data)
        drop_source.DoDragDrop(True)
        
        hp_drop_target = HPTextDropTarget(self.hp_files)
        self.hp_files.SetDropTarget(hp_drop_target)

        
    def disable_on_disconnect(self):
        # These two functions are pretty obvious. Clear and disable or
        # enable widgets and get the states of everything correct.
        self.hp_files.DeleteAllItems()
        self.hp_dir_label.SetLabelText('Not connected')
        # keep self.hp_files enabled
        self.hp_home_button.Disable()
        self.hp_dir_label.Disable()
        self.hp_updir_button.Disable()

        # except for these, which we re-enable
        self.kermit_radiobutton.Enable()
        self.xmodem_radiobutton.Enable()
        self.connect_button.Enable()
        self.serial_port_box.Enable()
        self.run_hp_command_item.Enable(False)

        
    def enable_on_connect(self):
        self.kermit_radiobutton.Disable()
        self.xmodem_radiobutton.Disable()
        self.serial_port_box.Disable()
        self.hp_home_button.Enable()
        self.hp_updir_button.Enable()
        self.hp_dir_label.Enable()
        self.hp_files.Enable()
        self.run_hp_command_item.Enable(True)
        
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
            self.run_hp_command_item.Enable(False)

            
    def set_kermit_ui_layout(self, event):
        self.xmodem_mode = False
        self.hp_dir_label.SetLabelText('')
        self.hp_files.DeleteAllItems()
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
        if self.connected:
            self.call_remote_directory()

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
        #self.SetStatusText('Updating local files...')
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
        #self.SetStatusText('Updated local files.')
        
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

        # Note that we don't save the selection index. Instead we rely
        # on the fact that the contents of a directory have unique
        # filenames, so we save the name and search for it later.
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

            if found_item_index != -1: # -1 is returned when the item is not found
                #print(self.local_files.GetItem(found_item_index))
                # find the item and make the listctrl select it.
                self.local_files.Select(found_item_index)

        # We don't tell the user (through the statusbar) that we
        # finished updating the local files /here/, because
        # populate_local files /always/ gets called. This one doesn't
        # always get called.


    def call_remote_directory(self):
        # same thing here as in the local update...
        self.hp_top_index = self.hp_files.GetTopItem()
        hp_sel_index = self.hp_files.GetFirstSelected()
        
        if hp_sel_index >= 0:
            self.hp_selection = self.hp_files.GetItem(
                hp_sel_index).GetText()
        else:
            self.hp_selection = None
        print('self.hp_selection', self.hp_selection)
        
        #self.SetStatusText('Updating remote variables...')
        # refresh the path by calling remote directory
        self.kermit_connector = KermitConnector()
            
        self.kermit = threading.Thread(
            target=self.kermit_connector.run,
            args=(StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())),
                  self,
                  'remote directory',
                  self.topic,
                  False))
            
        self.kermit.start()
    # This is very similar to refresh_local_files(). It saves the
    # selection, repopulates, and reselects.
    def reselect_hp_var(self):
        print('self.hp_selection in refresh', self.hp_selection)
        loc = self.hp_top_index + self.hp_files.GetCountPerPage() - 1
        # prevent an assertionerror when there is less
        # than one pagefull of files on the remote side
        if loc >= self.hp_files.GetCountPerPage():
            self.hp_files.EnsureVisible(loc)

        # select the previously selected item
        if self.hp_selection:
            found_item_index = self.hp_files.FindItem(0, self.hp_selection)
            if found_item_index != -1:
                self.hp_files.Select(found_item_index)

                
    def local_item_activated(self, event):
        sel_index = self.local_files.GetFirstSelected()
        # build a complete path to chdir to
        filename = Path(
            self.current_local_path,
            self.local_files.GetItem(sel_index).GetText())
        
        # make sure it's a directory
        # if it isn't a directory, we just don't do anything
        if filename.expanduser().is_dir():
            # if it is, update the path, picker, and file list
            self.current_local_path = filename
            self.local_dir_picker.SetPath(str(self.current_local_path))
            # populate, not refresh, because refresh has the selection
            # magic which we don't want to use here
            self.populate_local_files()

    def hp_item_activated(self, event):
        sel_index = self.hp_files.GetFirstSelected()
        varname = self.hpvars[sel_index].name

        if self.hpvars[sel_index].vtype == 'Directory':
            # this tells kermit_done() not to try to reselect a selected item
            self.new_remote_path = True
            print('varname', varname)
            
            self.SetStatusText(
                f'Changing calculator directory to {self.hp_selection}...')

            self.kermit_connector = KermitConnector()
            self.kermit = threading.Thread(
                target=self.kermit_connector.run,
                args=(StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())),
                      self,
                      'remote host ' + f'{varname}' + ' EVAL',
                      self.topic,
                      False))
            self.kermit.start()

    def send_menu_callback(self, event):
        index = self.local_files.GetFirstSelected()
        if index == -1:
            # nothing selected
            return
        
        file_path = Path(
            self.current_local_path,
            self.local_files.GetItemText(index))
        self.transfer_to_hp(file_path)

    def get_menu_callback(self, event):
        sel_index = self.hp_files.GetFirstSelected()
        if sel_index == -1:
            # nothing selected
            return
        self.transfer_to_local(sel_index)
                            
    def transfer_to_hp(self, path):
        print('start_hp_transfer, path is', path)
        # path is the file to send
        
        # see, normally we would have a statusbar update or a dialog
        # to inform the user when they can't send a file, but as long
        # as self.hp_files is disabled, we don't need that because the
        # drag and drop interface provides that feedback.

        filename = Path(path)
        
        
        # if self.hpvars is not defined yet, this will go
        # wrong. However, it shouldn't be possible, because in the
        # long run, I intend to make it impossible for the user to
        # open this dialog if the calculator isn't connected.
        if not hasattr(self, 'hpvars'):
            print('self.hpvars not defined yet')
            self.hpvars = []

        basename = Path(filename).name
        self.SetStatusText(f'Transferring {basename} to calculator...')

        msg = FileTools.create_local_message(
            filename.expanduser(), basename)
        exists = False
        for var in self.hpvars:
            if var.name == basename:
                exists = True
                
        FileSendDialog(
            parent=self,
            file_message=msg,
            port=StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())),
            # we have to give the dialog the full path so that
            # Kermit can get it
            filename=filename.expanduser(),
            file_already_exists=exists,
            use_xmodem=self.xmodem_mode,
            success_callback=self.refresh_all_files)

    def transfer_to_local(self, sel_index):
        index = int(sel_index)
        print('start_local_transfer, index is', index)
        var = self.hpvars[index]

        self.SetStatusText(f"Transferring '{var.name}' from calculator...")
        msg = f"You have chosen to transfer '{var.name}' from the HP48 at " + StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())) + '.'
        filestats = f'Size: {var.size}\nType: {var.vtype}\nChecksum: {var.crc}'


        FileGetDialog(
            parent=self,
            message=msg,
            file_message=filestats,
            port=StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())),
            varname=var.name,
            current_dir=self.current_local_path, 
            success_callback=self.refresh_all_files)
        
    def start_remote_command_dialog(self, event=None):
        RemoteCommandDialog(
            self,
            StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue()))).go()

    def process_kermit_data(self, output):
        # This function takes the output from Kermit, splits by lines
        # and finds each row (removing the one with the path and
        # memory free in Port 0), and then splits each row by columns
        # and returns it.

        self.hpvars = []
        lines = output.split('\n')
        
        # names can't have braces in them, so this is a valid way of
        # removing the line containing the path
        for line in lines:
            if '{' in line:
                lines.remove(lines[lines.index(line)])

        kermit_vars = [row.split() for row in lines]
        
        for i in kermit_vars:
            # each element of each row is the name, size, type, and
            # crc in that order
            
            # undo the thing we did in kermit_done()
            t = i[2]
            if t == 'RealNumber':
                t = 'Real Number'
            elif t == 'GlobalName':
                t = 'Global Name'
                
            self.hpvars.append(
                KermitVariable(name=i[0], size=i[1], vtype=t,
                               crc=KermitProcessTools.checksum_to_hexstr(i[3])))

        
        # clear the listctrl to refresh
        self.hp_files.DeleteAllItems()

        
        for index, var in enumerate(self.hpvars):
            item_index = self.hp_files.InsertItem(index, var.name)
            self.hp_files.SetItem(item_index, 1, var.size)
            self.hp_files.SetItem(item_index, 2, var.vtype)
            self.hp_files.SetItem(item_index, 3, var.crc)

        # auto resize the list in case lengths have changed
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
            StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())) + ' was cancelled.')

    def kermit_failed(self, cmd, out):
        # close this first because otherwise it lingers around confusingly
        if not self.connected:
            self.kermit_dialog.Close()
        # If Kermit failed, notify the user, correct various states,
        # and tell them what Kermit said (why it failed).
        print('kermit failed in HPex')
        print(out)
        if cmd == 'finish':
            self.SetStatusText("Couldn't finish Kermit server on " +
                               StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue()))
                               + '.')
            
            print('kermit failed on finish')
            KermitErrorDialog(self, out).Show(True)
            return




        # Kermit likes to add blank lines and other junk to the
        # output, so this just cleans those up.
        out = KermitProcessTools.strip_blank_lines(out)
        # do some stuff with Kermit's output and stderr
        KermitErrorDialog(self, out).Show(True)

        # empty the remote listctrl and return to disconnected mode
        self.hp_files.DeleteAllItems()
        self.connect_button.SetLabel('Connect') # just in case
        self.disable_on_disconnect()
        self.connected = False # also just in case
        self.SetStatusText(
            "Kermit couldn't reach " +
            StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())) + '.')


        # we must restore the drop targets here, because a failure
        # means they aren't restored in the drag callback
        self.make_drop_targets()
        
    def kermit_done(self, cmd, out):
        # This function is very large and quite complicated. Read
        # through to figure out what everything does.
        print('kermit_done in HPex')

        # strip the lines here like in kermit_failed
        out = KermitProcessTools.strip_blank_lines(out)

        #print('cmd:', cmd)
        #print('out:', out)

        # finish is a separate case because have to restore the UI
        if 'finish' in cmd:
            # restore various states, including the connect button,
            # too, so that the image put forward matches the text in
            # hp_dir_label
            self.disable_on_disconnect()
            # close the finishing dialog
            self.kermit_dialog.Close()
            self.connected = False
            self.connect_button.SetLabelText('Connect')

            self.SetStatusText('Finished Kermit server on ' +
                               StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())) +
                               '.')

        
        elif cmd == 'remote directory':
            if not self.connected:
                print('first connect')
                self.kermit_dialog.Close()
                

            # Real Number is two words, so it breaks a .split(' '). We
            # replace here and fix again later.
            
            # I think these are the only two-word types on the HP
            # 48. However, the Meta Kernel HPs have many more types. I
            # really need to get an HP 49.
            out = out.replace('Real Number', 'RealNumber')
            out = out.replace('Global Name', 'GlobalName')
            

            out = KermitProcessTools.remove_kermit_warnings(
                out.splitlines())

            # save the current selected item
            if self.connected:
                self.hp_top_index = self.hp_files.GetTopItem()
                hp_sel_index = self.hp_files.GetFirstSelected()
            
                if hp_sel_index >= 0:
                    self.hp_selection = self.hp_files.GetItem(
                        hp_sel_index).GetText()
                else:
                    self.hp_selection = None
            #print(out)
            # read these again to be processed
            self.hp_dir, self.memfree = KermitProcessTools.process_kermit_header(out)
            # update self.hpvars and the header above self.hp_files
            self.process_kermit_data(out)
            self.hp_dir_label.SetLabelText(
                f'{self.hp_dir}  {self.memfree} bytes free')
            
            # special things if we're already connected, that
            # means the user did a refresh or changed remote
            # directory
            if self.connected:
                # we adjust and update this here so, because
                # that's where the new data comes in. We also have
                # to only update this when we are connected.
                if self.new_remote_path:
                    self.new_remote_path = False
                    return
                else:
                    self.reselect_hp_var()
                    
                #self.SetStatusText('Updated remote variables.')
            else:
                self.SetStatusText(
                    'Connected to calculator on ' +
                        StringTools.trim_serial_port(
                            self.serial_port_box.GetValue()) + '.')

                print('connected')

                
            self.connect_button.SetLabel('Disconnect')
            self.enable_on_connect()
            self.connected = True
                            
            # don't disable connect_button here!
            # now, we can sort out Kermit's output and put it in
            # the list
            if self.firstpath:
                self.firstpath = self.hp_dir

                
        elif 'remote host' in cmd:
            # We changed directories.
            self.call_remote_directory()
            

    def connect_callback(self, event):
        # This function is responsible for both connecting and
        # disconnecting. If we're connected, we disconnect, and if
        # we're disconnected, we connect.

        # remove whitespace from the serial port box
        self.serial_port_box.SetValue(StringTools.trim_serial_port(self.serial_port_box.GetValue()))
        # do nothing if in XModem mode
        if self.xmodem_mode:
            return
        
        if StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())) == '':
            print('empty serial port box')
            wx.MessageDialog(self, 'Serial port box is empty!',
                             caption='Serial error',
                             style=wx.OK | wx.CENTRE | wx.ICON_ERROR).ShowModal()
            return
        
        self.kermit_connector = KermitConnector()
        
        if not self.connected:
            self.SetStatusText('Connecting to calculator...')

            # this will show automatically
            self.kermit_dialog = KermitConnectingDialog(
                self, self.kill_kermit_external,
                'Make sure the calculator is in Kermit server mode and set to translate mode 3.',
                'Connecting...')
            
            self.kermit = threading.Thread(
                target=self.kermit_connector.run,
                args=(StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())),
                      self,
                      'remote directory',
                      self.topic,
                      False))
            
        else:
            # the user can choose to reset the directory to the
            # starting directory (when we connected) on disconnect.
            cmd = ''
            if HPexSettingsTools.load_settings()['reset_directory_on_disconnect']:
                cmd += f'remote host {self.firstpath} EVAL,'
            self.kermit_dialog = KermitConnectingDialog(
                self, self.kill_kermit_external,
                'Finishing...',
                "Sending 'finish' to calculator...")
            
            # the event handler will take care of any troubles from
            # this

            self.kermit = threading.Thread(
                target=self.kermit_connector.run,
                #args=(StringTools.trim_serial_port(StringTools.trim_serial_port(self.serial_port_box.GetValue())),
                args=(StringTools.trim_serial_port(self.serial_port_box.GetValue()),
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
        self.kermit_dialog.Close()
        
            
    def close(self, event):
        if self.connected:
            # there's no reason to go through the whole process of
            # loading and reading the file if we aren't connected
            if HPexSettingsTools.load_settings()['disconnect_on_close']:
                # disconnect because we're now connected
                self.connect_callback(event=None)
            
        # If Kermit fails here, HPex will stop for a short moment
        # until Kermit gives up. I don't think this is an issue.
        self.Destroy()



if __name__ == '__main__':
    print("Don't run this file directly, run hpex.py to launch the HPex GUI.")
