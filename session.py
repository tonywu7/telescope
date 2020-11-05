import asyncio
import aiohttp

loop: asyncio.AbstractEventLoop = None
sem: asyncio.Semaphore = None
session: aiohttp.ClientSession = None


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
