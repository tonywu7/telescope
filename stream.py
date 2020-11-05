import logging
from pathlib import Path
from typing import List, Optional

import m3u8
import simplejson as json
import youtube_dl

from .session import get_semaphore, get_session
from .util import JSONDict, url_path_op

log = logging.getLogger('twitch_dl')
ytdl = youtube_dl.YoutubeDL({
    'download_archive': 'downloaded.txt',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:78.0) Gecko/20100101 Firefox/78.0',
    },
    'outtmpl': '%(upload_date)s [%(uploader)s] %(title).200s [%(extractor)s-%(id)s].%(ext)s',
    'logger': logging.getLogger('ytdl'),
})


class Stream:
    @classmethod
    async def from_url(cls, url):
        info = cls.get_info(url)
        stream = cls(info)
        await stream.load_m3u()
        return stream

    def __init__(self, info: JSONDict):
        self.info = info
        m3u = info.get('_m3u')
        if m3u:
            self.m3u = m3u8.loads(m3u['content'], m3u['uri'])

    @property
    def url(self) -> str:
        return self.info['webpage_url']

    @property
    def chat_url(self) -> Optional[str]:
        chat = self.info.get('subtitles', {}).get('rechat')
        if not chat:
            return None
        return chat[0]['url']

    @property
    def filename(self) -> Path:
        return Path(ytdl.prepare_filename(self.info))

    @property
    def filename_info(self) -> Path:
        return self.filename.with_suffix('.info.json')

    @property
    def filename_m3u(self) -> Path:
        return self.filename.with_suffix('.m3u8')

    @property
    def filename_m3u_norm(self) -> Path:
        return self.filename.with_suffix('.normalized.m3u8')

    @property
    def best_stream(self) -> Optional[str]:
        m3us = {}
        formats = self.info.get('formats')
        if not formats:
            return
        for f in formats:
            if f.get('protocol') != 'm3u8_native':
                continue
            width = f.get('width')
            if not width:
                continue
            m3us[width] = f['url']
        if not m3us:
            return
        return sorted(m3us.items())[-1][1]

    @property
    def m3u_normalized(self) -> m3u8.M3U8:
        normalized = m3u8.M3U8()
        KEYS = ('is_endlist', 'media_sequence', 'playlist_type', 'version', 'targetduration')
        normalized.data.update({k: self.m3u.data[k] for k in KEYS})
        normalized._initialize_attributes()
        for seg in self.m3u.segments:
            seg: m3u8.Segment
            kwargs = {'uri': seg.absolute_uri}
            if not seg.discontinuity:
                kwargs['duration'] = seg.duration
            else:
                name = Path(seg.absolute_uri).name
                name = name.split('-')[1]
                kwargs['uri'] = url_path_op(seg.absolute_uri, Path.with_name, name)
                kwargs['duration'] = 10.0
            normalized.add_segment(m3u8.Segment(**kwargs))
        return normalized

    @property
    def chat_replay(self) -> List[JSONDict]:
        return self.info.get('_chat_replay', [])

    async def load_m3u(self):
        url = self.best_stream
        async with get_session().get(url) as res:
            self.m3u = m3u8.loads(await res.text(), uri=url)

    async def load_chat(self):
        comments = []
        params = {}
        headers = {
            'Accept': 'application/vnd.twitchtv.v5+json; charset=UTF-8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/json; charset=UTF-8',
            'Origin': 'https://www.twitch.tv',
            'Referer': self.url,
        }
        url = self.chat_url
        if not url:
            return
        while True:
            log.debug(f'Downloading {url}')
            async with get_semaphore(), get_session().get(url, params=params, headers=headers) as res:
                data = await res.json()
                comments.extend(data['comments'])
                cursor = data.get('_next')
                if cursor:
                    params['cursor'] = cursor
                else:
                    break
        self.info['_chat_replay'] = comments

    def dump(self, output: Path):
        info_path = output / self.filename_info
        log.info(f'Dumping info to {info_path}')
        info = {**self.info}
        if self.m3u:
            info['_m3u'] = {
                'uri': self.m3u.base_uri,
                'content': self.m3u.dumps(),
            }
        with open(info_path, 'w+') as f:
            json.dump(info, f)

    @staticmethod
    def get_info(url: str) -> JSONDict:
        log.info(f'Extracting info from {url}')
        return ytdl.extract_info(url, download=False)
