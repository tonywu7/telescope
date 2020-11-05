import mimetypes
from pathlib import Path
from typing import Dict, List, Union
from urllib.parse import urlsplit, urlunsplit

import aiohttp

JSONType = Union[None, int, float, str, bool, List['JSONType'], Dict[str, 'JSONType']]
JSONDict = Dict[str, JSONType]


async def fetch(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as res:
        return await res.read(), res


async def download(session: aiohttp.ClientSession, url: str, filename: Path):
    print(f'Downloading {filename}')
    data, res = await fetch(session, url)
    suffix = mimetypes.guess_extension(res.content_type)
    if suffix:
        filename = filename.with_suffix(suffix)
    with open(filename, 'wb+') as f:
        f.write(data)
    return data, res


def url_path_op(url: str, func, *args, **kwargs) -> str:
    urlp = urlsplit(url)
    path = func(Path(urlp.path), *args, **kwargs)
    return urlunsplit((*urlp[:2], str(path), *urlp[3:]))
