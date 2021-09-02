import math, time

import curses
from curses.textpad import rectangle

import shlex, subprocess, select, signal

from .slot import Slot

class App:
    def __init__(self, stdscr):
        self.s = stdscr

        # initialize curses colors
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_BLUE)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_RED, -1)

        self.selected_slot = 0

        self.slots = []
        
        self.running = True
        self.show_help = False
        self.zoomed = None

    def load_configuration(self, conf):
        self.slots = [
            Slot(
                main_command = cfslot.get('run', None),
                working_directory = cfslot.get('workdir', None),
                restart_wait = cfslot.get('wait', None),
                watch = cfslot.get('watcher', None),
            ) 
            for cfslot in conf.get('slot', [])
        ]

    def draw_text(self, y, x, text, w=None, attr=0):
        if w is not None:
            text += " "*(w-len(text))
            text = text[:w]
        self.s.addstr(y, x, text, attr)

    def draw_slot(self, y, h, slot, selected=False):
        sy, sx = self.s.getmaxyx()
        # draw a rectangle around log
        rectangle(self.s, y, 0, y+h, sx-2)

        # fetch logs from slot
        lines = slot.log(h-1)
        
        ch = ' \u2588 ' if selected else '   '
        # draw status
        self.s.addstr(y, 6, 
                "{}{}{}".format(ch,slot.main_command,ch),
                curses.color_pair(1))

        if slot.status == "RUN":
            pass
        else:
            self.s.addstr(y, 1, "{}".format(slot.status), curses.color_pair(2))

        # if slot terminated with an exception show it
        if slot.exception is None:
            # draw logs
            for i,line in enumerate(lines):
                self.draw_text(y+i+1, 1, line, sx-3)
        else:
            # draw exception
            for i,line in enumerate(slot.exception):
                self.draw_text(y+i+1, 1, line, sx-3, attr=curses.color_pair(5))
        
        return y+h+1

    def draw_help(self):

        htxt = [
            " h   : show this window",
            " q,Q : quit mwatch",
            "",
            " ↑,↓ : change selection",
            "",
            " x   : extract slot",
            "",
            " r   : restart selected slot",
            " R   : restart all slots",
            " z   : zoom",
            " s   : stop select slot",
            " S   : stop all slots",
        ]

        sy, sx = self.s.getmaxyx()
        sry, srx = len(htxt)+1,50
        uly, ulx = int(sy/2 - sry/2), int(sx/2 - srx/2)
        rectangle(self.s, uly, ulx, int(sy/2 + sry/2), int(sx/2 + srx/2))

        for y,line in enumerate(htxt):
            self.draw_text(uly+y+1, ulx+1, line, srx-1, curses.color_pair(4))

    def handle_key(self, key):
        if key == curses.KEY_UP:
            self.selected_slot = max(self.selected_slot - 1, 0)

        elif key == curses.KEY_DOWN:
            self.selected_slot = min(self.selected_slot + 1, len(self.slots))

        elif key == ord('x'):
            slot = self.slots[self.selected_slot]
            slot.extract()

        elif key == ord('r'):
            # restart selected slot
            slot = self.slots[self.selected_slot]
            slot.restart()
        
        elif key == ord('R'):
            # restart all slots
            for slot in self.slots:
                slot.restart()

        elif key == ord('s'):
            slot = self.slots[self.selected_slot]
            slot.terminate()
        
        elif key == ord('S'):
            for slot in self.slots:
                slot.terminate()

        elif key == ord('z'):
            if self.selected_slot == self.zoomed:
                self.zoomed = None
            else:
                self.zoomed = self.selected_slot

        elif key in [ord('q'), ord('Q')]:
            self.running = False
        
        elif key in [ord('h'), ord('H')]:
            self.show_help = not self.show_help

    def main(self):
 
        for s in self.slots:
            s.start()

        # configure curses
        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)
        self.s.keypad(True)

        try:
            while self.running:
                # clear screen
                self.s.clear()

                sy, sx = self.s.getmaxyx()
                ns = len(self.slots)

                # iterate over slots and draw them
                ny = 0
                for idx,slot in enumerate(self.slots):
                    # compute slot height
                    if self.zoomed is None:
                        h = math.floor(sy / ns) - 1
                    else:
                        if self.zoomed == idx:
                            h = sy - ns*4
                        else:
                            h = 4

                    ny = self.draw_slot(ny, h, slot, idx == self.selected_slot)

                self.s.addstr(sy-1, sx-10, "[h]elp", curses.color_pair(3))
                
                if self.show_help:
                    self.draw_help()

                time.sleep(0.1)
                self.s.refresh()

                self.s.nodelay(True)
                try:
                    self.handle_key(self.s.getch())
                except curses.error:
                    pass
        except Exception as e:
            raise
        except KeyboardInterrupt:
            pass

        for s in self.slots:
            s.terminate()
        for s in self.slots:
            s.join()

