import signal

import wx
from pubsub import pub
import ptyprocess

from settings import HPexSettingsTools

# Kermit, even with set quiet on, will still let stale lock warnings
# through. Therefore, we still have to filter it.
class KermitConnector:
    """A class to manage the challenge of dealing with Kermit and the
    various states it can handle. It generates events in the master HPex
    class depending on the outcome of Kermit or the user's choice to
    cancel."""
    
    def run(self, port, parent, command, ptopic,
            do_newdata_event=True, use_callafter=True,
            alt_options=None):
        # when wx isn't running, CallAfter is unnecessary and actually
        # doesn't even work.
        """Connect to the calculator and run `command`."""
        
        self.cancelled = False
        self.parent = parent
        self.command = command
        self.ptopic = ptopic
        self.use_callafter = use_callafter
        # options:
        #     -Y  | don't read ~/.kermrc
        #     -H  | suppress herald and greeting
        #     -B  | Kermit is in background mode
        #     -C  | run these commands
        #     -l  | use this port
        #     -b  | use this speed
        
        # the idea to use 'set file display crt' comes from HPTalx. It
        # simplifies the file transfer status thing to be less
        # terminal-demanding and easier to read from an automated
        # program.

        # 'set file names literal' tells Kermit to note the
        # capitalization of the 48 filenames.
        
        # 'set send timeout 1', 'set receive timeout 1', and 'set
        # retry-limit 1' all tell Kermit not to wait very long for
        # packets.
        invocation = ['kermit', '-Y', '-H', '-C', 'set parity none,set flow none,set carrier-watch off,set modem type direct,set block 3,set control prefix all,set protocol kermit,set send timeout 1,set receive timeout 1,set retry-limit 1,set file display crt,set file names literal,set hints off,set quiet on,']

        # load alt_options if we choose to use them, otherwise, use
        # the settings file
        if not alt_options:
            settings = HPexSettingsTools.load_settings()
        else:
            settings = alt_options
            
        file_mode = settings.file_mode
        if file_mode == 'Binary':
            invocation[-1] += 'set file type binary,'
        elif file_mode == 'ASCII':
            invocation[-1] += 'set file type text,'
        # no else, we just won't do anything if it's set to Auto
        
        parity = settings.parity
        # '0 (None)', '1 (Odd)', '2 (Even)', '3 (Mark)', '4 (Space)'
        
        # we check if the number is in the parity value, because the
        # CLI uses just numbers
        if parity == '0 (None)':
            invocation[-1] += 'set parity none,'
        elif parity == '1 (Odd)':
            invocation[-1] += 'set parity odd,'
        elif parity == '2 (Even)':
            invocation[-1] += 'set parity even,'
        elif parity == '3 (Mark)':
            invocation[-1] += 'set parity mark,'
        elif parity == '4 (Space)':
            invocation[-1] += 'set parity space,'

        cksum = settings.kermit_cksum
        # kermit_cksum is just a number in a string, so we can append
        # it directly

        invocation[-1] += f'set block {cksum},'

        invocation[-1] += self.command
        # without 'exit' in here, Kermit never finishes
        
        invocation[-1] += ',exit'
        invocation.append('-l')
        invocation.append(port)
        invocation.append('-b')
        invocation.append(settings.baud_rate)


        self.proc = ptyprocess.PtyProcessUnicode.spawn(invocation)
        
        self.out = ''


        while True:
            try:
                # remote directory needs readline(), to work
                if self.command == 'remote directory':
                    self.line = self.proc.readline()
                    
                #self.out += remove_control_characters(
                 #   self.proc.readline()) + '\n'
                 
                # Kermit's updating progress looks like this:
                #SF
                #X to cancel file,  CR to resend current packet
                #Z to cancel group, A for status report
                #E to send Error packet, Ctrl-C to quit immediately: 
                #kermit.c => KERMIT.C => KERMIT.C
                #Size: 13190, Type: text, ascii => ascii
                #    File   Percent       Packet
                #    Bytes  Done     CPS  Length
                #      155    1%   17132      94 E

                # Kermit's progress bar should be at least 40 bytes or
                # so
                else:
                    self.line = self.proc.read(40)
                    #remove_control_characters(self.proc.read(1))

                # replace ASCII bell characters with nothing so the
                # terminal emulator doesn't annoyingly notify the user
                # (that is, when HPex prints the output).
                self.line = self.line.replace(chr(7), '')
                self.out += self.line
                
                # This is the line in the weird terminal thing Kermit
                # does that shows the percentage of the file transfer
                # complete
               
                # helps us know whether to send this to the calling
                # class
                if do_newdata_event:
                    #print('sending data')
                    if self.use_callafter:
                        wx.CallAfter(
                            pub.sendMessage,
                            f'kermit.newdata.{self.ptopic}',
                            data=self.line,
                            cmd=self.command)
                    else:
                        # do it directly
                        pub.sendMessage(
                            f'kermit.newdata.{self.ptopic}',
                            data=self.line,
                            cmd=self.command)

            except (OSError, IOError, EOFError) as err:
                print('finished or failed, err:', err)
                break
            
        returncode = self.proc.wait()
        if not self.cancelled:
            if returncode != 0:
                # By using threading.Thread (not multiprocess,
                # unfortunately), CallAfter works. Don't ask me why.

                #print('posted event')
                if self.use_callafter:
                    wx.CallAfter(
                        pub.sendMessage,
                        f'kermit.failed.{self.ptopic}',
                        cmd=self.command,
                        out=self.out)
                else:
                    pub.sendMessage(
                        f'kermit.failed.{self.ptopic}',
                        cmd=self.command,
                        out=self.out)

                return
            
            if self.use_callafter:
                wx.CallAfter(
                    pub.sendMessage,
                    f'kermit.done.{self.ptopic}',
                    cmd=self.command,
                    out=self.out)
            else:
                pub.sendMessage(
                    f'kermit.done.{self.ptopic}',
                    cmd=self.command,
                    out=self.out)

        else:
            # return code would always be nonzero
            if self.use_callafter:
                wx.CallAfter(
                    pub.sendMessage,
                    f'kermit.cancelled.{self.ptopic}',
                    cmd=self.command,
                    out=self.out)
            else:
                pub.sendMessage(
                    f'kermit.cancelled.{self.ptopic}',
                    cmd=self.command,
                    out=self.out)

    def cancel_kermit(self):
        print('cancelling')

        # Telling Kermit to stop with an "x" or an "e" is unreliable
        # at best. If we kill the process directly, then it will
        # stop. However, that means that both file transfer dialogs
        # have to have the "press [ATTN] or [CANCEL]" message.
        
        self.kill_kermit()
        self.cancelled = True


        if self.use_callafter:
            wx.CallAfter(
                pub.sendMessage,
                f'kermit.cancelled.{self.ptopic}',
                cmd=self.command,
                out=self.out)
        else:
            pub.sendMessage(
                f'kermit.cancelled.{self.ptopic}',
                cmd=self.command,
                out=self.out)

    def kill_kermit(self):
        # just let the run() function take care of
        # this. self.cancelled is monitored to control the event data
        # generated.
        self.cancelled = True
        self.proc.kill(signal.SIGKILL)

    def isalive(self):
        return self.proc.isalive()
