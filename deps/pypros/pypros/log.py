import logging

class TerminalColor:
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GREY = '\033[0m'  # normal
    WHITE = '\033[1m'  # bright white
    UNDERLINE = '\033[4m'

def set_level_color(lev, color):
    logging.addLevelName(lev, "{}{}{}".format(color, logging.getLevelName(lev)[0], TerminalColor.GREY))

set_level_color(logging.DEBUG,      TerminalColor.GREY)
set_level_color(logging.INFO,       TerminalColor.WHITE)
set_level_color(logging.WARNING,    TerminalColor.YELLOW)
set_level_color(logging.ERROR,      TerminalColor.RED)
set_level_color(logging.CRITICAL,   TerminalColor.MAGENTA)
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y.%m.%d %I:%M:%S %p', level=logging.DEBUG)

log = logging
