import logging
import platform
from functools import partial
from logging.handlers import QueueHandler
from multiprocessing import get_context
from pathlib import Path

import pexpect
import streamlink
from pexpect.popen_spawn import PopenSpawn
from streamlink.stream.hls import HLSStream

from .util import colored as _

MP_METHODS = {
    'Darwin': 'forkserver',
    'Linux': 'fork',
    'Windows': 'spawn',
}

try:
    ctx = get_context(MP_METHODS[platform.system()])
except ValueError:
    ctx = get_context('spawn')


def _reconfig_logging():
    _level_to_name = {
        logging.CRITICAL: 'CRITICAL', logging.ERROR: 'ERROR', logging.WARN: 'WARNING',
        logging.INFO: 'INFO', logging.DEBUG: 'DEBUG', 5: 'TRACE', logging.NOTSET: 'NOTSET',
    }
    for level, name in _level_to_name.items():
        logging.addLevelName(level, name)


_reconfig_logging()


class StreamlinkFFmpeg(ctx.Process):
    def __init__(
        self, url: str, filename: Path, closing: ctx.Event,
        log_queue: ctx.Queue, err_queue: ctx.Queue,
        *args, **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.closing = closing
        self.log_queue = log_queue
        self.err_queue = err_queue
        self.url = url
        self.output = Path(filename)

    def config_logging(self):
        handler = QueueHandler(self.log_queue)
        root = logging.getLogger()
        for h in root.handlers:
            root.removeHandler(h)
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        self.log = logging.getLogger('main')
        self.fflog = logging.getLogger('ffmpeg')

    def open_stream(self, quality: str = 'best') -> HLSStream:
        return streamlink.streams(self.url)[quality]

    def open_ffmpeg(self) -> PopenSpawn:
        return PopenSpawn(['ffmpeg', '-y', '-i', 'pipe:', '-c', 'copy', str(self.output.resolve())])

    def run(self):
        self.config_logging()
        self.log.info(_('Starting Streamlink-FFmpeg', color='magenta'))

        try:
            stream = self.open_stream()
            reader = stream.open()
            self.log.info(f'Selected stream {stream.url}')

            ffmpeg = self.open_ffmpeg()
            output = ffmpeg.compile_pattern_list([
                pexpect.EOF, pexpect.TIMEOUT, r'.+\n', r'.+\r',
            ])

            try:
                for data in iter(partial(reader.read, 65536), b''):
                    ffmpeg.send(data)
                    while True:
                        exp = ffmpeg.expect_list(output, timeout=.1)
                        if exp < 3:
                            break
                        self.fflog.info(ffmpeg.match.group(0).decode('utf8').strip())
            except KeyboardInterrupt:
                self.log.info('Exiting normally. Received SIGINT.')

            ffmpeg.sendeof()
            ffmpeg.wait()
            self.fflog.info(_('Encoding finished', color='green'))
            for line in ffmpeg.readlines():
                self.fflog.info(line.decode('utf8').strip())

            reader.close()

        except BaseException as e:
            self.log.error(e, exc_info=e)
        finally:
            self.closing.set()
