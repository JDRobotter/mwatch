import math, time

import curses
from curses.textpad import rectangle

from .slot import Slot

class App:
    def __init__(self, stdscr):
        self.s = stdscr

        # initialize curses colors
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_BLUE)
        curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)

        self.selected_slot = 0

        self.slots = []
        
        self.running = True
        self.show_help = False

    def load_configuration(self, conf):
        self.slots = [
            Slot(
                main_command = cfslot.get('run', None),
                working_directory = cfslot.get('workdir', None),
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

        # draw logs
        for i,line in enumerate(lines):
            self.draw_text(y+i+1, 1, line, sx-3)
        
        return y+h+1

    def draw_help(self):

        htxt = [
            " h   : show this window",
            " q,Q : quit mwatch",
            "",
            " ↑,↓ : change selection",
            "",
            " r   : restart selected slot",
            " R   : restart all slots",
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

        elif key == ord('r'):
            # restart selected slot
            slot = self.slots[self.selected_slot]
            slot.restart()
        
        elif key == ord('R'):
            # restart all slots
            for slot in self.slots:
                slot.restart()

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
                    h = math.floor(sy / ns) - 1
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

        except KeyboardInterrupt:
            pass

        for s in self.slots:
            s.kill()
        for s in self.slots:
            s.join()

