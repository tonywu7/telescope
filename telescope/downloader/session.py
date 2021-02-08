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

import asyncio
import logging
import mimetypes
from pathlib import Path

import aiohttp

loop: asyncio.AbstractEventLoop = None
sem: asyncio.Semaphore = None
session: aiohttp.ClientSession = None
log = logging.getLogger('aiohttp.session')


def init(*, concurrency=1):
    global loop
    global sem
    global session

    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(concurrency, loop=loop)
    session = aiohttp.ClientSession(
        loop=loop,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:82.0) Gecko/20100101 Firefox/82.0',
        },
    )


def get_session():
    return session


def get_semaphore():
    return sem


async def close_session():
    await session.close()


async def fetch(url: str):
    async with sem, session.get(url) as res:
        return await res.read(), res


async def download(url: str, filename: Path):
    log.debug(f'Downloading {filename}')
    data, res = await fetch(url)
    suffix = mimetypes.guess_extension(res.content_type)
    if suffix:
        filename = filename.with_suffix(suffix)
    with open(filename, 'wb+') as f:
        f.write(data)
    return data, res
