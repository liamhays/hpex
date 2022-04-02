import threading
import os
import platform

_system = platform.system()

import wx
from pubsub import pub

if _system != 'Windows':
    from hpex.kermit_pubsub import KermitConnector
#from xmodem_pubsub import XModemConnector
from hpex.helpers import FileTools, KermitProcessTools



class KermitConnectingDialog(wx.Frame):
    def __init__(self, parent, callback, message, title):
        wx.Frame.__init__(self, parent, title=title)
        self.connecting_dialog_sizer = wx.BoxSizer(wx.VERTICAL)

        self.connecting_dialog_sizer.Add(
            wx.StaticText(
                self,
                wx.ID_ANY,
                message),
            1,
            wx.ALL | wx.ALIGN_CENTER)
        
        self.connecting_cancel_button = wx.Button(
            self,
            wx.ID_CANCEL,
            'Cancel')
        
        self.connecting_cancel_button.Bind(
            wx.EVT_BUTTON,
            callback.__call__)
        
        self.connecting_dialog_sizer.Add(
            self.connecting_cancel_button,
            1,
            wx.EXPAND | wx.ALL)
        
        self.SetSizerAndFit(
            self.connecting_dialog_sizer)

        self.Show(True)
        self.Update() # force a draw

        
class KermitErrorDialog(wx.Frame):
    def __init__(self, parent, stdout, title='Kermit Error',
                 close_func=None):
        wx.Frame.__init__(self, parent, title=title)
        self.parent = parent
        self.close_func = close_func

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(
            wx.StaticText(
                self,
                wx.ID_ANY,
                "Kermit failed, with this error:"), 
            0,
            wx.EXPAND | wx.ALL)
            
        self.stdoutbox = wx.StaticBoxSizer(
            wx.VERTICAL, self, '')
        
        self.stdoutbox.Add(
            wx.StaticText(
                self.stdoutbox.GetStaticBox(),
                wx.ID_ANY,
                KermitProcessTools.strip_blank_lines(stdout),
                style=wx.TE_MULTILINE | wx.TE_READONLY),
            1,
            wx.EXPAND | wx.ALL)

        self.close_button = wx.Button(self, wx.ID_CLOSE, 'Close')
        self.close_button.Bind(wx.EVT_BUTTON, self.on_close)
        
        self.sizer.Add(
            self.stdoutbox, 1, wx.EXPAND | wx.ALL)

        self.sizer.Add(
            self.close_button, 0, wx.EXPAND | wx.ALL)

        self.SetSizerAndFit(self.sizer)

    def on_close(self, event):

        if callable(self.close_func):
            self.close_func.__call__()

        self.Close()


class XModemErrorDialog(wx.Frame):
    def __init__(self, parent, boxmessage, close_func=None):
        wx.Frame.__init__(self, parent, title='XModem Error')
        self.parent = parent
        
        self.close_func = close_func
        
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.sizer.Add(
            wx.StaticText(
                self,
                wx.ID_ANY,
                boxmessage,
                style=wx.TE_MULTILINE | wx.TE_READONLY),
            1,
            wx.EXPAND | wx.ALL)

        self.close_button = wx.Button(self, wx.ID_CLOSE, 'Close')
        self.close_button.Bind(wx.EVT_BUTTON, self.on_close)
        
        self.sizer.Add(
            self.close_button, 0, wx.EXPAND | wx.ALL)

        self.SetSizerAndFit(self.sizer)

    def on_close(self, event):
        if self.close_func:
            self.close_func.__call__()
        self.Close()

        
class ObjectInfoDialog(wx.Frame):
    def __init__(self, parent, initdir):
        wx.Frame.__init__(self, parent, title='HP48 Object Info')
        # Default Windows background color is weird grey (this code is
        # in other Frames as well)
        if _system == 'Windows':
            self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENU))
        self.initdir = initdir
        
    def go(self, event=None):
        self.sizer = wx.BoxSizer(wx.VERTICAL) # needed to hold the panel
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        # for whatever reason, a Panel will process keyboard events
        # but the Frame will not.
        self.main_panel = wx.Panel(self)
        self.file_picker = wx.FilePickerCtrl(
            self, wx.ID_ANY, '',
            style=wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST)
        
        self.file_picker.SetInitialDirectory(str(self.initdir))
        
        self.file_picker.Bind(
            wx.EVT_FILEPICKER_CHANGED, self.update_file_info_box)
        
        self.file_info_box = wx.StaticBoxSizer(
            wx.VERTICAL, self, 'File info')
        
        self.file_info = wx.StaticText(
            self.file_info_box.GetStaticBox(),
            wx.ID_ANY,
            'Choose a file with the box above.')
        
        self.file_info_box.Add(
            self.file_info,
            1,
            wx.EXPAND | wx.ALL)

        self.main_sizer.Add(self.file_picker, 0, wx.EXPAND | wx.ALL)
        self.main_sizer.Add(self.file_info_box, 1, wx.EXPAND | wx.ALL)
        self.main_panel.SetSizer(self.main_sizer)
        
        self.sizer.Add(self.main_panel)
        self.SetSizerAndFit(self.sizer)

        self.main_panel.SetFocus()

        # this is so that we can use Esc to close
        # (I found myself trying to use Esc to close this dialog and
        # realized it should be a feature)
        self.main_panel.Bind(wx.EVT_KEY_DOWN, self.keydown)
        self.Show(True)
        

    def keydown(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            
    def update_file_info_box(self, event):
        #print(self.file_picker.GetPath())
        self.file_info.SetLabelText(
            FileTools.create_local_message(
                self.file_picker.GetPath(),
                os.path.split(self.file_picker.GetPath())[1]))
        # we have to have this here so that the window's size is
        # updated accordingly.
        self.Fit()

# TODO: this should have red/green or similar colors to distinguish send and receive
class RemoteCommandDialog(wx.Frame):
    def __init__(self, parent, port):
        wx.Frame.__init__(self, parent, title='Run Remote Command')

        self.parent = parent
        self.port = port

    def go(self):
        self.topic = 'RemoteCommandDialog'
        
        pub.subscribe(
            self.kermit_newdata, f'kermit.newdata.{self.topic}')
        pub.subscribe(
            self.kermit_failed, f'kermit.failed.{self.topic}')
        pub.subscribe(
            self.kermit_cancelled, f'kermit.cancelled.{self.topic}')
        pub.subscribe(self.kermit_done, f'kermit.done.{self.topic}')


        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.entry_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.command_box = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.command_box.SetHint('Type a command and hit enter...')
        self.command_box.Bind(wx.EVT_TEXT_ENTER, self.run_command)
        
        self.go_button = wx.Button(self, wx.ID_ANY, 'Go')
        self.go_button.Bind(wx.EVT_BUTTON, self.run_command)
        
        # without this, at least on Plasma, the button is really short
        # compared to the box
        self.go_button.SetMinSize(self.command_box.GetSize())
        self.output_box = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY)

        self.cancel_button = wx.Button(self, wx.ID_CANCEL, 'Cancel')
        self.cancel_button.Bind(wx.EVT_BUTTON, self.cancel_kermit)
        self.cancel_button.Disable()
        
        # we need the command box to be proportionally significantly
        # larger than the button
        self.entry_sizer.Add(self.command_box, 2, 0, 0)
        self.entry_sizer.Add(self.go_button, 0, 0, 0)

        self.main_sizer.Add(self.entry_sizer, 0, wx.EXPAND | wx.ALL)
        self.main_sizer.Add(
            wx.StaticText(
                self,
                wx.ID_ANY,
                'Calculator response:'))
        
        self.main_sizer.Add(self.output_box, 1, wx.EXPAND | wx.ALL)

        self.main_sizer.Add(self.cancel_button, 0, wx.EXPAND | wx.ALL)

        self.SetSizer(self.main_sizer)
        # must be after the sizer and fit
        self.SetMinSize(self.parent.GetSize())

        self.Fit()
        # take focus away from command_box so that the user can see
        # the hint
        self.output_box.SetFocus()
        self.Show(True)

    def cancel_kermit(self, event):
        # we have to use kill here, for whatever reason
        
        # I think it's because Kermit is even less willing to stop
        # with a 'remote host'
        self.kermit_connector.kill_kermit()
        
    def kermit_newdata(self, data, cmd):
        self.output_box.AppendText(data)
            
    def kermit_done(self, cmd, out):
        self.output_box.AppendText('\nKermit finished successfully')
        # clear the command box if we succeeded, don't if we
        # failed or cancelled
        self.command_box.Clear()
        self.cancel_button.Disable()
        
    def kermit_failed(self, cmd, out):
        self.output_box.AppendText('\nKermit failed')
        self.cancel_button.Disable()
        
    def kermit_cancelled(self, cmd, out):
        self.output_box.AppendText('\nKermit cancelled')
        self.cancel_button.Disable()
        
    def run_command(self, event):
        # if we have a backslash on the end of the line, then kermit
        # will exit and lead to multiple instances, each with a
        # lock. This leads to blocking in the application, and makes
        # it so you can't finish the calculator server.

        # I think we can replace single backslashes with double
        # backslashes, because those don't cause Kermit to exit.
        cmd = self.command_box.GetValue().replace('\\','\\\\')
        self.output_box.AppendText(f'\n\nSending "{cmd}"...\n')
        
        self.kermit_connector = KermitConnector()

        self.kermit = threading.Thread(
            target=self.kermit_connector.run,
            args=(self.port,
                  self,
                  'remote host ' + cmd,
                  self.topic))

        self.kermit.start()
        self.cancel_button.Enable()
