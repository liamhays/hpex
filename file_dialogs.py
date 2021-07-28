import threading
import os
import pathlib

import wx
from pubsub import pub
from kermit_pubsub import KermitConnector
from xmodem_pubsub import XModemConnector

from dialogs import KermitErrorDialog, XModemErrorDialog
from helpers import KermitProcessTools, XModemProcessTools
from settings import HPexSettingsTools


class FileSendDialog(wx.Frame):
    def __init__(self, parent, title, message,
                 file_message, port, filename,
                 remote_files, use_xmodem=False,
                 success_callback=None):
        
        wx.Frame.__init__(self, parent, title=title)
        
        self.port = port
        self.filename = filename
        self.basename = str(pathlib.Path(filename).name)
        self.parent = parent
        self.xmodem = use_xmodem
        self.success_callback = success_callback

        self.overwrite = False
        # no remote files in XModem mode

        self.topic = 'FileSendDialog'

        # ask for overwriting, but note that it only matters in Kermit
        # mode and if the user wants it.

        ask = HPexSettingsTools.load_settings().ask_for_overwrite
        if self.basename in remote_files and not self.xmodem and ask:
            self.result = wx.MessageDialog(
                self,
                f"'{filename}' already exists on the calculator.\nDo you want to continue?\nIf overwriting is disabled on the calculator, files will become '{filename}.1', '{filename}.2', etc.",
                'File already exists',
                wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT).ShowModal()
            print(self.result)
            # ID_CANCEL results from the user closing the dialog with
            # the window manager's close button. We make it mean "no".
            if self.result == wx.ID_NO or self.result == wx.ID_CANCEL:
                self.Destroy()

            # if the user answered yes, keep going (we can't really
            # control overwriting on the calculator).
                
                
        pub.subscribe(
            self.kermit_newdata, f'kermit.newdata.{self.topic}')
        pub.subscribe(
            self.kermit_failed, f'kermit.failed.{self.topic}')
        pub.subscribe(
            self.kermit_cancelled, f'kermit.cancelled.{self.topic}')
        pub.subscribe(self.kermit_done, f'kermit.done.{self.topic}')


        pub.subscribe(
            self.xmodem_newdata, f'xmodem.newdata.{self.topic}')
        pub.subscribe(
            self.xmodem_failed, f'xmodem.failed.{self.topic}')
        pub.subscribe(
            self.serial_port_error,
            f'xmodem.serial_port_error.{self.topic}')
        pub.subscribe(
            self.xmodem_cancelled, f'xmodem.cancelled.{self.topic}')
        pub.subscribe(self.xmodem_done, f'xmodem.done.{self.topic}')
        # for some reason, closing the window with the close button
        #after doing something with kermit causes a RuntimeError
        
        self.transfer_sizer = wx.BoxSizer(wx.VERTICAL)

        self.label_sizer = wx.BoxSizer(wx.VERTICAL)

        self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.label_sizer.Add(
            wx.StaticText(
                self,
                wx.ID_ANY,
                message),
            0,
            wx.EXPAND | wx.ALL)

        self.file_contents_box = wx.StaticBoxSizer(
            wx.VERTICAL, self, 'File info')

        self.file_contents_box.Add(
            wx.StaticText(
                self.file_contents_box.GetStaticBox(),
                wx.ID_ANY,
                file_message),
            1,
            wx.EXPAND | wx.ALL)
        
        self.label_sizer.Add(self.file_contents_box)

        # only show this if we're in Kermit mode
        if not self.xmodem:
            self.as_name_sizer = wx.BoxSizer(wx.HORIZONTAL)
            self.as_name_box = wx.TextCtrl(self)
            
            self.as_name_sizer.Add(
                wx.StaticText(
                    self,
                    wx.ID_ANY,
                    'Rename on calculator:'),
                wx.ALIGN_CENTER_VERTICAL)
            self.as_name_sizer.Add(
                self.as_name_box, wx.EXPAND | wx.RIGHT)
            self.as_name_box.SetValue(self.basename)
            self.label_sizer.Add(self.as_name_sizer)
        
        self.progress_text = wx.StaticText(
            self,
            wx.ID_ANY,
            'Progress:')

        self.label_sizer.Add(
            self.progress_text,
            1,
            wx.EXPAND | wx.ALL | wx.ALIGN_LEFT)
        
        self.progress_bar = wx.Gauge(self)
        self.label_sizer.Add(self.progress_bar, 1, wx.EXPAND)
        
        self.cancel_button = wx.Button(
            self, wx.ID_CANCEL, 'Cancel')

        self.cancel_button.Disable()

        self.copy_button = wx.Button(
            self, wx.ID_ANY, 'Copy', name='copybutton')

        self.button_sizer.Add(
            self.copy_button, 1, wx.EXPAND | wx.ALL)

        self.button_sizer.Add(
            self.cancel_button, 1, wx.EXPAND | wx.ALL)

        self.copy_button.Bind(wx.EVT_BUTTON, self.run_transfer)
        self.cancel_button.Bind(wx.EVT_BUTTON, self.cancel)
        
        self.transfer_sizer.Add(
            self.label_sizer, 0,
            wx.EXPAND | wx.ALL)
            
        self.transfer_sizer.Add(
            self.button_sizer, 0,
            wx.EXPAND | wx.ALL)

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.SetSizerAndFit(self.transfer_sizer)

        self.Show(True)
        self.Update()



    def kermit_newdata(self, data, cmd):
        # if kermit fails, we'll get an empty value, which will cause
        # an error
        # we don't need to note that error, because it will be caught
        # by self.kermit_response
        #print('data', data)
        p = KermitProcessTools.kermit_line_to_progress(data)
        #print('p', p)
        if p is not None:
            self.progress_text.SetLabelText(f'Progress: {p}%')
            # set the progress bar to the value
            self.progress_bar.SetValue(p)


    def reset_progress(self, extra_text=''):
        # reset the progress bar and, optionally, the text on the
        # label.
        self.progress_text.SetLabelText('Progress:' + extra_text)
        self.progress_bar.SetValue(0)
        self.cancel_button.Disable()
        self.copy_button.Enable()
        
    def xmodem_newdata(self, file_count, total,
                       success, error, should_update):

        if should_update:
            # update everything
            progress = XModemProcessTools.packet_count_to_progress(
                success, file_count)
            self.progress_bar.SetValue(progress)
            self.progress_text.SetLabelText(
                'Progress: ' + str(progress) + '%')
        

    def serial_port_error(self):
        print('serial port error')
        self.parent.SetStatusText(
            f'Serial port at {self.port} unreachable.')
        self.cancel_button.Disable()
        XModemErrorDialog(
            self,
            f"HPex couldn't access {self.port}. Is it present? Try rescanning and trying to send the file again.",
            # then, reset the progress bar so that we're not confusing
            # the user.
            lambda: self.reset_progress('')).Show(True)
        
    def xmodem_failed(self):
        print('FileSendDialog: xmodem failed')
        self.parent.SetStatusText(
            f'XModem failed to write to {self.port}.')
        self.cancel_button.Disable()
        XModemErrorDialog(
            self,
            f"XModem couldn't write to the HP48 at {self.port}. Check the calculator for any error messages, and verify your setup.",
            # same here
            lambda: self.reset_progress('')).Show(True)
        
        
    def xmodem_done(self, file_count, total, success, error):
        # xmodem worked, clear stuff up
        self.reset_progress(' Done!')

    def xmodem_cancelled(self, file_count):
        self.reset_progress(' XModem transfer cancelled.')
        self.parent.SetStatusText(
            f'XModem file copy to {self.port} cancelled.')


    def kermit_failed(self, cmd, out):
        print('kermit failed')

        # messagedialog with boxes saying what happened
        self.parent.SetStatusText(
            f'Kermit failed to copy {self.filename} to {self.port}.')
        self.cancel_button.Disable()
        out = KermitProcessTools.strip_blank_lines(out)
        q_lines = ''
        for line in out.split('\n'):
            if '?' in line:
                q_lines += line + '\n'
                
        KermitErrorDialog(
            self, q_lines,
            close_func=self.reset_progress).Show(True)
        
        # don't close, so that the user can close themselves or
        # try again without having to restart the dialog. I could
        # see that getting very annoying.

    def kermit_cancelled(self, cmd, out):
        print('kermit cancelled in FileSendDialog')
        self.parent.SetStatusText(
            f'Kermit file transfer to {self.port} cancelled')
        self.reset_progress(
            extra_text=' Kermit cancelled; you may have to press [ATTN] or [CANCEL].')
        self.Fit()

    def kermit_done(self, cmd, out):
        print('kermit succeeded')

        self.reset_progress(extra_text=' Done!')
        
        if callable(self.success_callback):
            self.success_callback.__call__()
        

    def run_transfer(self, event):
        if not self.xmodem:
            command = ''
            # the user wants a different name
            if self.as_name_box.GetValue() != self.basename:
                asname = self.as_name_box.GetValue()
                command += f'send /as-name:{asname} {self.filename}'
            else:
                command += f'send {self.filename}'
                
            print(command)
            # this code is basically the same as the connecting code
            self.kermit_connector = KermitConnector()
            
            self.kermit = threading.Thread(
                target=self.kermit_connector.run,
                args=(self.port, self, command, self.topic))
            

            
            self.kermit.start()

        else:
            self.xmodem_connector = XModemConnector()
            self.xmodem = threading.Thread(
                target=self.xmodem_connector.run,
                args=(self.port, self,
                      self.filename, self.topic))

            self.xmodem.start()

            self.reset_progress(' Run XRECV now.')

        self.copy_button.Disable()
        self.cancel_button.Enable()
        
    def cancel(self, event):
        if not self.xmodem:
            if self.kermit_connector.isalive():
                self.kermit_connector.cancel_kermit()
                self.copy_button.Enable()
        else:
            self.xmodem_connector.cancel()
            self.copy_button.Enable()

    def on_close(self, event):
        # unsubscribe to prevent accessing deleted objects
        # from https://stackoverflow.com/a/62105716
        pub.unsubscribe(
            self.kermit_newdata, f'kermit.newdata.{self.topic}')
        pub.unsubscribe(
            self.kermit_failed, f'kermit.failed.{self.topic}')
        pub.unsubscribe(
            self.kermit_cancelled, f'kermit.cancelled.{self.topic}')
        pub.unsubscribe(self.kermit_done, f'kermit.done.{self.topic}')


        pub.unsubscribe(
            self.xmodem_newdata, f'xmodem.newdata.{self.topic}')
        pub.unsubscribe(
            self.xmodem_failed, f'xmodem.failed.{self.topic}')
        pub.unsubscribe(
            self.serial_port_error,
            f'xmodem.serial_port_error.{self.topic}')
        pub.unsubscribe(
            self.xmodem_cancelled, f'xmodem.cancelled.{self.topic}')
        pub.unsubscribe(self.xmodem_done, f'xmodem.done.{self.topic}')

        self.Destroy()
        
class FileGetDialog(wx.Frame):
    def __init__(self, parent, title, message,
                 file_message, port, filename,
                 current_dir,
                 success_callback=None):
        
        wx.Frame.__init__(self, parent, title=title)
        
        self.port = port
        self.filename = filename
        self.parent = parent
        self.current_dir = current_dir
        self.success_callback = success_callback

        self.topic = 'FileGetDialog'
        self.overwrite = False
        #print(os.listdir(self.current_dir))

        # check for the file in the current local directory, if it
        # exists, ask about overwriting
        ask = HPexSettingsTools.load_settings().ask_for_overwrite
        if self.filename in os.listdir(self.current_dir) and ask:
            # just let the user know, so that they know what will
            # happen
            self.result = wx.MessageDialog(
                self,
                f"'{filename}' already exists in " +
                str(self.current_dir) +
                f".\nDo you want to overwrite the existing file?\nIf you don't choose to overwrite, files will become '{filename}.~1~', '{filename}.~2~', etc.",
                'File already exists',
                wx.YES_NO | wx.ICON_QUESTION | wx.CANCEL | wx.NO_DEFAULT).ShowModal()
            if self.result == wx.ID_YES:
                self.overwrite = True
            elif self.result == wx.ID_NO:
                self.overwrite = False
            # on this one, we actually want to have a cancel option,
            # because the user could decide to stop the operation
            elif self.result == wx.ID_CANCEL:
                self.Destroy()

        pub.subscribe(
            self.kermit_newdata, f'kermit.newdata.{self.topic}')
        pub.subscribe(
            self.kermit_failed, f'kermit.failed.{self.topic}')
        pub.subscribe(
            self.kermit_cancelled, f'kermit.cancelled.{self.topic}')
        pub.subscribe(self.kermit_done, f'kermit.done.{self.topic}')

        # for some reason, closing the window with the close button
        # after doing something with kermit causes a RuntimeError
        
        self.transfer_sizer = wx.BoxSizer(wx.VERTICAL)

        self.label_sizer = wx.BoxSizer(wx.VERTICAL)

        self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.label_sizer.Add(
            wx.StaticText(
                self,
                wx.ID_ANY,
                message),
            0,
            wx.EXPAND | wx.ALL)

        self.file_contents_box = wx.StaticBoxSizer(
            wx.VERTICAL, self, 'File info')

        self.file_contents_box.Add(
            wx.StaticText(
                self.file_contents_box.GetStaticBox(),
                wx.ID_ANY,
                file_message),
            1,
            wx.EXPAND | wx.ALL)

        self.label_sizer.Add(self.file_contents_box)

        self.progress_text = wx.StaticText(
            self,
            wx.ID_ANY,
            'Progress:')
        
        self.label_sizer.Add(
            self.progress_text,
            1,
            wx.EXPAND | wx.ALL)
        
        
        self.cancel_button = wx.Button(
            self, wx.ID_CANCEL, 'Cancel')

        self.cancel_button.Disable()

        self.copy_button = wx.Button(
            self, wx.ID_ANY, 'Copy', name='copybutton')

        self.button_sizer.Add(
            self.copy_button, 1, wx.EXPAND | wx.ALL)

        self.button_sizer.Add(
            self.cancel_button, 1, wx.EXPAND | wx.ALL)

        self.copy_button.Bind(wx.EVT_BUTTON, self.run_kermit)
        self.cancel_button.Bind(wx.EVT_BUTTON, self.cancel)
        
        self.transfer_sizer.Add(
            self.label_sizer, 0,
            wx.EXPAND | wx.ALL)
            
        self.transfer_sizer.Add(
            self.button_sizer, 1,
            wx.EXPAND | wx.ALL)

        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.SetSizerAndFit(self.transfer_sizer)

        self.Show(True)
        self.Update()

    def reset_progress(self, extra_text=''):
        self.progress_text.SetLabelText('Progress:' + extra_text)
        self.cancel_button.Disable()
        self.copy_button.Enable()
        
    def kermit_newdata(self, data, cmd):
        if not self.already_wrote_label:
            self.already_wrote_label = True
            self.progress_text.SetLabelText(
                'Progress: not available when receiving')
        

    def kermit_failed(self, cmd, out):
        print('kermit failed')

        self.parent.SetStatusText(
            f'Kermit failed to transfer {self.filename} from {self.port}')
        self.cancel_button.Disable()
        out = KermitProcessTools.strip_blank_lines(out)
        q_lines = ''
        for line in out.split('\n'):
            if '?' in line:
                q_lines += line + '\n'
                
        KermitErrorDialog(
            self, q_lines,
            close_func=self.reset_progress).Show(True)
        # don't close, so that the user can close themselves or
        # try again without having to restart the dialog. I could
        # see that getting very annoying.

    def kermit_cancelled(self, cmd, out):
        self.parent.SetStatusText('Kermit file transfer cancelled')
        self.reset_progress(
            extra_text=' Kermit cancelled; you may have to press [ATTN] or [CANCEL].')

        
    def kermit_done(self, cmd, out):
        self.parent.SetStatusText(
            f'Successfully transferred {self.filename}.')
        print('kermit succeeded')
        self.reset_progress(extra_text=' Done!')
        if callable(self.success_callback):
            self.success_callback.__call__()
            
    def run_kermit(self, event):
        # we're not going to worry about moving, because we can't
        # differentiate easily between directories and variables

        if self.overwrite:
            command = 'set file collision overwrite,'
        else:
            command = ''
        # move to the right directory
        command += 'cd ' + str(self.current_dir) + ','
        command += f'get {self.filename}'
        print(command)
        # this code is basically the same as the connecting code
        self.kermit_connector = KermitConnector()
        
        self.kermit = threading.Thread(
            target=self.kermit_connector.run,
            args=(self.port, self, command, self.topic))
        
        
        
        self.kermit.start()
        # lets us check if we've already written 'Progress: not
        # available when receiving' to self.progress_text
        self.already_wrote_label = False
        self.copy_button.Disable()
        self.cancel_button.Enable()
        
    def cancel(self, event):
        if self.kermit_connector.isalive():
            self.kermit_connector.cancel_kermit()
            self.copy_button.Enable()


    
    def onClose(self, event):
        pub.unsubscribe(
            self.kermit_newdata, f'kermit.newdata.{self.topic}')
        pub.unsubscribe(
            self.kermit_failed, f'kermit.failed.{self.topic}')
        pub.unsubscribe(
            self.kermit_cancelled, f'kermit.cancelled.{self.topic}')
        pub.unsubscribe(self.kermit_done, f'kermit.done.{self.topic}')

        self.Destroy()
