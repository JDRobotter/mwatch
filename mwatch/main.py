import time
import argparse
import curses

import toml

from .app import App
from .slot import Slot
from .watcher import FileWatcher

def main():
 
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawDescriptionHelpFormatter,
                epilog="""
Create a TOML configuration file listing what you want to execute.
Here is an example configuration:

    [[slot]]
        run = "nc -vlp 3920"
        workdir = "/tmp/"
        watch = "/tmp/source/"

    [[slot]]
        run = "sleep 3600"
                """,
            )
    parser.add_argument("conf", help="configuration file")

    args = parser.parse_args()

    # load configuration from TOML file
    conf = toml.load(args.conf)

    # run curses application
    def _wrapper(stdscr):
        app = App(stdscr)
        app.load_configuration(conf)
        app.main()
    try:
        curses.wrapper(_wrapper)
    except Exception as e:
        pass

if __name__ == '__main__':
    main()
