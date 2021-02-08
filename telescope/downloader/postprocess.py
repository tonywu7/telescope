# postprocess.py
# Copyright (C) 2021  Tony Wu +https://github.com/tonywu7/
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import tempfile
from pathlib import Path

from ..util.ffmpeg import (FFmpegException, concat_mts, get_start_time,
                           trim_overlap)
from .stream import TwitchStream


async def extend_stream(url: str, segment_dir: Path, output: Path = None, suffix='.mts'):
    log = logging.getLogger('postprocess')

    segments = [*sorted(p for p in Path(segment_dir).iterdir() if p.suffix == suffix)]
    first = str(segments[0])

    start = await get_start_time(first)
    outpoint = start + 60

    video: TwitchStream = await TwitchStream.from_url(url)

    if output:
        output = Path(output)
    else:
        output = Path('.') / video.filename

    with tempfile.TemporaryDirectory() as tempdir:
        tempdir = Path(tempdir)

        head = tempdir / 'head.mts'
        await video.pipe_stream(video.m3u_normalized(), head,
                                '-to', str(outpoint), '-c', 'copy')

        trimmed = tempdir / 'trimmed.mts'
        await trim_overlap(head, first, trimmed)

        try:
            await concat_mts([trimmed, *segments], output or video.filename)
        except FFmpegException as e:
            log.error('Error concatenating files:')
            log.error(e.stderr)
            raise
