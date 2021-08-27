import os,sys,time,fcntl
from threading import Thread, Lock
from queue import Queue, Empty
import shlex, subprocess, select, signal

from .watcher import FileWatcher

class Slot(Thread):
    def __init__(self,
            main_command=None,
            working_directory=None,
            restart_wait=0,
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

        self.readline_buffer = b""
        self.logqueue = Queue()

        self.restart_on_exit = True
        self.asked_to_quit = False

        self.loglines = []

        self.status = ""

    def no_blocking_readlines(self):
        # wait for data on process stdout
        fno = self.process.stdout.fileno()
        rs,_,_ = select.select([fno,],[],[],0.1)

        if fno in rs:
            # read block, append to buffer and cut it into lines
            buf = self.process.stdout.read(1024)
            self.readline_buffer += buf
            
            lines = self.readline_buffer.split(b'\n')

            self.readline_buffer = lines[-1]
            return lines[:-1]

        return None

    def kill(self):
        self.asked_to_quit = True
        self.restart_on_exit = False
        self.status = "KILL"
        
        # check if process as exited
        code = self.process.poll()
        if code is None:
            # get process group ID from process PID
            os.killpg(self.process.pid, signal.SIGKILL)

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

    def gracefull_terminate(self):
        self.status = "TERM"
        self.process.terminate()

        def _check_restart_wrapper():
            try:
                # give process some time to quit
                # after TERM before upgrading to KILL
                rv = self.process.wait(5)
        
            except subprocess.TimeoutExpired:
                # kill process
                self.status = "KILL"
                self.process.kill()

            except Exception as e:
                print(e)

            self.loglines = []
            self.status = "STOP"

        Thread(target=_check_restart_wrapper).start()

    def run(self):

        first_time = True

        while True:

            if self.asked_to_quit:
                break

            if not first_time:
                time.sleep(self.restart_wait)

            while not self.restart_on_exit:
                time.sleep(0.3)

            # clear logs
            self.loglines = []

            self.status = "RUN"

            # run main command
            self.run_main_command()

    def run_main_command(self):
        # split command to args
        args = shlex.split(self.main_command)

        # fork subprocess
        self.process = subprocess.Popen(args,
                            close_fds=True,
                            preexec_fn=os.setsid,
                            stdin = subprocess.PIPE,
                            stdout = subprocess.PIPE,
                            stderr = subprocess.STDOUT,
                            cwd = self.working_directory,
                            env = os.environ,
                        )
    

        # make stdout non-blocking
        fd = self.process.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl|os.O_NONBLOCK)

        while True:

            # check if watcher as detected changes
            if self.watcher and self.watcher.check():
                self.restart()

            # append new line to queue
            lines = self.no_blocking_readlines()
            if lines is not None:
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

