
import os
from gi.repository import GLib
import multiprocessing

# This should be removed. Instead implement the same functionality inside Pipe.
class GProcess(multiprocessing.Process):
    """A queue object that also wakes up the GLib mainloop if data is received.
    This works by opening a pair of FDs."""

    def start(self, *args, **kwargs):
        # Start the processes ...
        multiprocessing.Process.start(self, *args, **kwargs)

        # And register the pipe in the mainloop of the main process
        GLib.io_add_watch(self.pipe_r, GLib.IO_IN | GLib.IO_PRI, self._child_event)

    def __init__(self, *args, **kwargs):
        if 'childcb' in kwargs:
            self._child_event_cb = kwargs.pop('childcb')
        else:
            self._child_event_cb = None

        multiprocessing.Process.__init__(self, *args, **kwargs)

        # Create a pair of pipes
        self.pipe_r, self.pipe_w = os.pipe()

    def wake_parent(self):
        os.write(self.pipe_w, ' ')

    def _child_event(self, iocontext, event):
        os.read(self.pipe_r, 1)
        try:
            self.child_event()
        except Exception, e:
            import traceback
            traceback.print_exc()
        return True

    def child_event(self):
        if self._child_event_cb is not None:
            self._child_event_cb(self)

