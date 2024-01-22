#  Copyright (c) Cyan Changes 2024. All rights reserved.

import importlib
import atexit

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

from debounce import debounce


class HMRHandler(FileSystemEventHandler):
    def __init__(self, module, hmr_obj):
        super().__init__()
        self.module = module
        self.hmr_obj = hmr_obj

    @debounce(0.5)
    def on_modified(self, event: FileModifiedEvent):
        try:
            self.hmr_obj.__module__ = importlib.reload(self.module)
        except ImportError:
            pass


def hmr(module):
    module_file = module.__file__
    observer = Observer()

    hmr_obj = type('HMRObject', (), {
        "__module__": module,
        "__getattribute__": lambda self, p: getattr(type(self).__module__, p)
    })

    observer.schedule(HMRHandler(module, hmr_obj), module_file)
    observer.start()
    atexit.register(observer.stop)
    return hmr_obj()
