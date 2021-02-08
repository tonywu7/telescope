import logging
import platform
from functools import partial
from logging.handlers import QueueHandler
from multiprocessing import get_context
from pathlib import Path
from typing import Tuple

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

    def open_stream(self, qualities: Tuple[str] = ('best', '1080p', '720p')) -> HLSStream:
        streams = streamlink.streams(self.url)
        for q in qualities:
            try:
                return streams[q]
            except KeyError:
                pass

    def open_ffmpeg(self) -> PopenSpawn:
        return PopenSpawn(['ffmpeg', '-y', '-i', 'pipe:', '-c', 'copy', str(self.output.resolve())])

    def run_streamlink(self):
        self.config_logging()
        self.log.info(_('Starting Streamlink-FFmpeg', color='magenta'))

        try:
            stream = self.open_stream()
            if not stream:
                raise RuntimeError('No stream can be selected')
    
            self.log.info(f'Selected stream {stream.url}')

            ffmpeg = self.open_ffmpeg()
            output = ffmpeg.compile_pattern_list([
                pexpect.EOF, pexpect.TIMEOUT, r'.+\n', r'.+\r',
            ])

            reader = stream.open()
            io = iter(partial(reader.read, 65536), b'')
            try:
                while True:
                    try:
                        data = next(io)
                    except IOError:
                        reader = stream.open()
                        io = iter(partial(reader.read, 65536), b'')
                        continue
                    ffmpeg.send(data)
                    while True:
                        exp = ffmpeg.expect_list(output, timeout=.1)
                        if exp < 3:
                            break
                        self.fflog.info(ffmpeg.match.group(0).decode('utf8').strip())
            except StopIteration:
                reader.close()
            except KeyboardInterrupt:
                self.log.info('Exiting normally. Received SIGINT.')

            ffmpeg.sendeof()
            ffmpeg.wait()
            self.fflog.info(_('Encoding finished', color='green'))
            for line in ffmpeg.readlines():
                self.fflog.info(line.decode('utf8').strip())

        except BaseException as e:
            self.log.error(e, exc_info=e)
        finally:
            self.closing.set()

    def run_ffmpeg(self):
        self.config_logging()
        self.log.info(_('Starting Streamlink-FFmpeg', color='magenta'))

        stream = None
        for i in range(5):
            stream = self.open_stream()
            if stream:
                break

        if not stream:
            self.log.error('Error opening stream.')
            self.closing.set()
            return

        self.log.info(f'Selected stream {stream.url}')

        name = self.output.with_suffix('').name
        ffmpeg = PopenSpawn(['ffmpeg', '-y', '-protocol_whitelist', 'file,http,https,tcp,tls,pipe',
                             '-i', stream.url, '-strftime', '1', '-f', 'ssegment', '-c', 'copy', '-copyts',
                             self.output.with_name(f'{name}.%Y%m%d.%H%M%S.mts')])
        output = ffmpeg.compile_pattern_list([
            pexpect.EOF, pexpect.TIMEOUT, r'.+\n', r'.+\r',
        ])

        try:
            while True:
                exp = ffmpeg.expect_list(output, timeout=.1)
                if exp == 0:
                    break
                if exp > 1:
                    self.fflog.info(ffmpeg.match.group(0).decode('utf8').strip())
        except BaseException as e:
            self.log.error(e, exc_info=e)
        except KeyboardInterrupt:
            self.log.info('Exiting normally. Received SIGINT.')

        ffmpeg.sendeof()
        ffmpeg.wait()
        self.fflog.info(_('Encoding finished', color='green'))
        for line in ffmpeg.readlines():
            self.fflog.info(line.decode('utf8').strip())

    def run(self):
        self.run_ffmpeg()
