import asyncio
import sys
from pathlib import Path

from .session import init, close_session
from .stream import Stream


async def main(url, wd, *args, **kwargs):
    wd = Path(wd)
    init(concurrency=32)

    video = await Stream.from_url(url)
    # await video.load_chat()
    video.dump(wd)
    with open('a.m3u8', 'w+') as f:
        f.write(video.m3u_normalized.dumps())

    await close_session()


if __name__ == '__main__':
    asyncio.run(main(*sys.argv[1:]))
