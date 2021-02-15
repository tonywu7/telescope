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
from typing import Dict

import pendulum
from aiohttp import web

from ..util import LOG_LISTENER

log = logging.getLogger('handler')


async def test_webhook(req: web.Request, data: Dict[str, str], server: web.Application):
    log.info(data)


async def streamlink_start(req: web.Request, data: Dict[str, str], server: web.Application):
    from .stream import StreamlinkFFmpeg, ctx
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
