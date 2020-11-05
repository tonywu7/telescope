from pathlib import Path
from typing import Dict, List, Union
from urllib.parse import urlsplit, urlunsplit

JSONType = Union[None, int, float, str, bool, List['JSONType'], Dict[str, 'JSONType']]
JSONDict = Dict[str, JSONType]


def url_path_op(url: str, func, *args, **kwargs) -> str:
    urlp = urlsplit(url)
    path = func(Path(urlp.path), *args, **kwargs)
    return urlunsplit((*urlp[:2], str(path), *urlp[3:]))
