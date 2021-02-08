# MIT License
#
# Copyright (c) 2020 Tony Wu +https://github.com/tonywu7
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import logging
from logging.handlers import QueueListener
from multiprocessing import Queue

log = logging.getLogger('main.utils')


class RobustQueueListener(QueueListener):
    def _monitor(self):
        try:
            super()._monitor()
        except EOFError:
            log.warning('Log listener has prematurely stopped.')


class QueueListenerWrapper:
    def __init__(self):
        self.queue = None
        self.listener = None

    def enable(self):
        if self.queue:
            return self.queue
        self.queue = Queue()
        self.listener = RobustQueueListener(self.queue, *logging.getLogger().handlers, respect_handler_level=True)
        self.listener.start()
        return self.queue

    def disable(self):
        if not self.queue:
            return
        self.listener.stop()
        self.queue = None
        self.listener = None

    def start(self):
        if not self.listener:
            return
        if not self.listener._thread:
            self.listener.start()
        return self.queue

    def stop(self):
        if not self.listener:
            return
        if self.listener._thread:
            self.listener.stop()
        return self.queue


LOG_LISTENER = QueueListenerWrapper()
