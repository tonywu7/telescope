# MIT License
#
# Copyright (c) 2021 Tony Wu +https://github.com/tonywu7/
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

from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

from multidict import MultiDict


class URLParam(MultiDict):
    @classmethod
    def from_parse_qs(cls, qs_res: Dict[str, List[str]]):
        md = cls()
        for k, v in qs_res.items():
            for s in v:
                md.add(k, s)
        return md

    def query_string(self):
        kvp = []
        for k, v in self.items():
            kvp.append(f'{quote(str(k))}={quote(str(v))}')
        return '&'.join(kvp)

    def update_url(self, url: str):
        urlp = urlsplit(url)
        query = URLParam.from_parse_qs(parse_qs(urlp.query))
        query.update(self)
        return urlunsplit([*urlp[:3], query.query_string(), *urlp[4:]])


def url_path_op(url: str, func, *args, **kwargs) -> str:
    urlp = urlsplit(url)
    path = func(Path(urlp.path), *args, **kwargs)
    return urlunsplit((*urlp[:2], str(path), *urlp[3:]))
