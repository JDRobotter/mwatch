import os,sys,time,fcntl
from threading import Thread, Lock
from queue import Queue, Empty
import shlex, subprocess, select, signal
import tempfile, stat

from .watcher import FileWatcher

class Slot(Thread):
    def __init__(self,
            main_command=None,
            working_directory=None,
            restart_wait=None,
            watch=None):
        Thread.__init__(self, daemon=True)
        self.main_command = main_command
        self.working_directory = working_directory
        self.restart_wait = restart_wait

        if watch is not None:
            self.watcher = FileWatcher(watch)
        else:
            self.watcher = None

        self.process = None

        self.stdout_readline_buffer = b""
        self.stderr_readline_buffer = b""
        self.logqueue = Queue()

        self.restart_on_exit = True
        self.asked_to_quit = False

        self.loglines = []
        self.status = ""
        self.exception = None

    def no_blocking_readlines(self):
        # wait for data on process stdout
        ofno = self.process.stdout.fileno()
        efno = self.process.stderr.fileno()
        rs,_,_ = select.select([ofno,efno],[],[],0.1)

        merged_lines = []
        if efno in rs:
            # read block, append to buffer and cut it into lines
            buf = self.process.stderr.read(1024)
            self.stderr_readline_buffer += buf

            lines = self.stderr_readline_buffer.split(b'\n')

            self.stderr_readline_buffer = lines[-1]

            merged_lines.extend(lines[:-1])

        if ofno in rs:
            # read block, append to buffer and cut it into lines
            buf = self.process.stdout.read(1024)
            self.stdout_readline_buffer += buf
            
            lines = self.stdout_readline_buffer.split(b'\n')

            self.stdout_readline_buffer = lines[-1]

            merged_lines.extend(lines[:-1])


        return merged_lines

    def send_signal(self, s):
        if self.process.poll() is not None:
            return
        pgid = os.getpgid(self.process.pid)
        if pgid > 0:
            os.killpg(pgid, s)

    def kill(self):
        self.asked_to_quit = True
        self.restart_on_exit = False
        self.status = "KILL"
        
        # check if process as exited
        code = self.process.poll()
        if code is None:
            self.send_signal(signal.SIGKILL)

    def join(self):
        self.process.wait()

    def restart(self):
        self.asked_to_quit = False
        self.restart_on_exit = True
        self.gracefull_terminate()

    def terminate(self):
        self.asked_to_quit = False
        self.restart_on_exit = False
        self.gracefull_terminate()

    def extract(self):
        self.asked_to_quit = False
        self.restart_on_exit = False

        def _on_exit():

            ft = tempfile.NamedTemporaryFile(mode="w", delete=False)
            ft.write("""
                #!/usr/bin/env bash
                source $HOME/.bashrc
                cd {}
                history -s '{}'
                {}
            """.format(self.working_directory, self.main_command, self.main_command))

            ft.close()

            args = shlex.split("gnome-terminal -- bash --init-file {}".format(ft.name))
            p = subprocess.Popen(args)
            p.poll()

        self.gracefull_terminate(_on_exit)

    def gracefull_terminate(self, on_exit=None):
        self.status = "TERM"
        self.send_signal(signal.SIGTERM)

        def _check_restart_wrapper():
            try:
                # give process some time to quit
                # after TERM before upgrading to KILL
                rv = self.process.wait(5)
        
            except subprocess.TimeoutExpired:
                # kill process
                self.status = "KILL"
                self.send_signal(signal.SIGKILL)

            except Exception as e:
                print(e)

            self.loglines = []

            if on_exit:
                on_exit()

        Thread(target=_check_restart_wrapper).start()

    def run(self):
        try:
            self.safe_run()
        except Exception as e:
            etype, evalue, etb = sys.exc_info()
            import traceback
            tb_text = [str(e)]
            for filename,line,function,text in traceback.extract_tb(etb):
                tb_text.append(" - in file {}:{}, in {} : {}".format(
                    filename, line, function, text
                ))

            self.exception = tb_text

    def safe_run(self):

        while True:

            if self.asked_to_quit:
                break

            while not self.restart_on_exit:
                time.sleep(0.3)

            # clear logs
            self.loglines = []

            self.status = "RUN"

            # run main command
            self.run_main_command()

            if self.restart_wait is not None:
                time.sleep(self.restart_wait)

    def run_main_command(self):
        # split args
        args = shlex.split(self.main_command)

        # fork subprocess
        self.process = subprocess.Popen(args,
                            preexec_fn = os.setsid,
                            stdin = None,
                            stdout = subprocess.PIPE,
                            stderr = subprocess.PIPE,
                            cwd = self.working_directory,
                            env = {
                                **os.environ,
                                'PYTHONUNBUFFERED': '1',
                            },
                        )

        # make stdout non-blocking
        fd = self.process.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl|os.O_NONBLOCK)

        # make stderr non-blocking
        fd = self.process.stderr.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl|os.O_NONBLOCK)

        while True:

            # check if watcher as detected changes
            if self.watcher and self.watcher.check():
                self.restart()

            # append new line to queue
            lines = self.no_blocking_readlines()
            for line in lines:
                line = line.decode()
                self.logqueue.put(line.strip())
            
            # check if process as exited
            code = self.process.poll()
            if code is not None:
                break
        
    def log(self, limit):
        # empty queue into loglines
        try:
            while True:
                self.loglines.append( self.logqueue.get(False) )
        except Empty:
            pass
        
        # limite loglines size
        self.loglines = self.loglines[-100:]

        return self.loglines[-limit:]

