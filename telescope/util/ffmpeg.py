# Copyright 2021 Tony Wu +https://github.com/tonywu7/
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import subprocess
import tempfile
from asyncio.subprocess import create_subprocess_exec as run_async
from pathlib import Path
from typing import List

from audio_offset_finder import find_offset

log = logging.getLogger('mpegts')


class FFmpegException(RuntimeError):
    def __init__(self, stderr: bytes):
        super().__init__('ffmpeg/ffprobe returned a non-zero exit code')
        self.stderr = stderr.decode('utf8')


async def run_ffmpeg(args: List[str], in_=None, *, executable='ffmpeg',
                     capture=subprocess.PIPE) -> bytes:
    proc = await run_async(executable, *args, stderr=capture, stdout=capture)
    stdout, stderr = await proc.communicate(in_)
    if proc.returncode != 0:
        raise FFmpegException(stderr)
    return stdout


async def get_start_time(file) -> float:
    args = '-v error -show_entries format=start_time -of default=noprint_wrappers=1:nokey=1'.split(' ')
    return float(await run_ffmpeg([*args, file], executable='ffprobe'))


async def trim_overlap(head: Path, segment: Path, output: Path):
    offset, score = find_offset(str(head), str(segment))
    log.info(f'Offset: {offset}s')
    await run_ffmpeg(['-i', str(head), '-to', str(offset), '-c', 'copy', str(output)])


async def concat_mts(segments: List[Path], output: Path, genpts=True, faststart=True):
    with tempfile.NamedTemporaryFile() as f:
        for s in segments:
            f.write(f"file '{str(s.resolve(True))}'\n".encode('utf8'))
        prefix = ['-fflags', '+genpts'] if genpts else []
        faststart = ['-movflags', 'faststart'] if faststart else []
        await run_ffmpeg([*prefix, '-f', 'concat', '-safe', '0',
                          '-i', str(Path(f.name).resolve()), *faststart,
                          '-c', 'copy', str(output)],
                         capture=None)
