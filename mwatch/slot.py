import os,sys,time,fcntl
from threading import Thread, Lock
from queue import Queue, Empty
import shlex, subprocess, select, signal

class Slot(Thread):
    def __init__(self, main_command=None, working_directory=None):
        Thread.__init__(self, daemon=True)
        self.main_command = main_command
        self.working_directory = working_directory

        self.process = None

        self.readline_buffer = b""
        self.logqueue = Queue()

        self.restart_on_exit = True

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
        self.restart_on_exit = False
        self.status = "KILL"
        
        # get process group ID from process PID
        pgid = os.getpgid(self.process.pid)
        os.killpg(pgid, signal.SIGKILL)

    def join(self):
        self.process.wait()

    def restart(self):
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

        Thread(target=_check_restart_wrapper).start()

    def run(self):

        while self.restart_on_exit:

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
            # append new line to queue
            #line = self.process.stdout.readline()
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

