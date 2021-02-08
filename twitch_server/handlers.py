# MIT License
#
# Copyright (c) 2020 Tony Wu <tony[dot]wu(at)nyu[dot]edu>
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
from typing import Dict

import pendulum
from aiohttp import web

from twitch_server.stream import StreamlinkFFmpeg, ctx
from twitch_server.util import LOG_LISTENER

log = logging.getLogger('handler')


async def test_webhook(req: web.Request, data: Dict[str, str], server: web.Application):
    log.info(data)


async def streamlink_start(req: web.Request, data: Dict[str, str], server: web.Application):
    user_name = data['user_name']
    url = f'https://twitch.tv/{user_name}'
    timestamp = pendulum.now()
    file_name = server['OUTPUT_PATH'] / f'{user_name}-{timestamp.strftime("%y%m%d.%H%M%S")}.mts'

    log_queue = LOG_LISTENER.start()
    err_queue = ctx.Queue()
    closing = ctx.Event()

    proc = StreamlinkFFmpeg(url, file_name, closing, log_queue, err_queue)
    proc.start()
    return proc
