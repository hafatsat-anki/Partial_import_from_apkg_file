# Copyright: Ren Tatsumoto <tatsu at autistici.org>
# Copyright (c) 2023 mizmu addons 
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
from typing import Optional, TextIO

from aqt import mw, gui_hooks

from .config import config

ADDON_NAME = 'Partial import from apkg file'


class LogDebug:
    _logfile: Optional[TextIO] = None
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        gui_hooks.profile_will_close.append(self.close)

    def write(self, msg: str) -> None:
        print('CroPro debug:', str(msg))
        if not config['enable_debug_log']:
            return
        if not self._logfile:
            path = os.path.join(mw.pm.base, 'cropro.log')
            print(f'CroPro debug: opening log file "{path}"')
            self._logfile = open(path, 'a')
        self._logfile.write(str(msg) + '\n')
        self._logfile.flush()

    def __call__(self, *args, **kwargs):
        return self.write(*args, **kwargs)

    def close(self):
        if self._logfile and not self._logfile.closed:
            self.write("closing debug log.")
            self._logfile = self._logfile.close()
