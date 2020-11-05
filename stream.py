import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import List, Optional

import m3u8
import simplejson as json
import youtube_dl

from .session import download, get_semaphore, get_session
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

M3U_ATTRS = ('is_endlist', 'media_sequence', 'playlist_type', 'version', 'targetduration')
RE_TRIMMED_SEG = re.compile(r'\d+v\d+-(\d+)\.ts')


class HLS:
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
        else:
            self.m3u = None

    @property
    def url(self) -> str:
        return self.info['webpage_url']

    @property
    def filename(self) -> Path:
        return Path(ytdl.prepare_filename(self.info))

    @property
    def filename_info(self) -> Path:
        return self.filename.with_suffix('.json')

    @property
    def filename_thumbnail(self) -> Path:
        return self.filename.with_suffix('.jpg')

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
    def best_thumbnail(self) -> Optional[str]:
        thumbs = self.info.get('thumbnails', [])
        return sorted(thumbs, key=lambda t: t.get('preference', 0))[-1]['url']

    @property
    def chat_replay(self) -> List[JSONDict]:
        return self.info.get('_chat_replay', [])

    async def load_m3u(self, refresh=False):
        if self.m3u and not refresh:
            return
        log.info(f'Downloading playlist for {self.url}')
        url = self.best_stream
        async with get_session().get(url) as res:
            self.m3u = m3u8.loads(await res.text(), uri=url)

    def m3u_normalized(self) -> m3u8.M3U8:
        normalized = m3u8.M3U8()
        normalized.data.update({k: self.m3u.data[k] for k in M3U_ATTRS})
        normalized._initialize_attributes()
        for seg in self.m3u.segments:
            seg: m3u8.Segment
            kwargs = {'uri': seg.absolute_uri,
                      'discontinuity': seg.discontinuity,
                      'duration': seg.duration}
            normalized.add_segment(m3u8.Segment(**kwargs))
        return normalized

    async def load_thumbnail(self):
        log.info(f'Downloading thumbnail for {self.url}')
        url = self.best_thumbnail
        if not url:
            return
        await download(url, self.filename_thumbnail)

    async def load_stream(self, out='.', stream=None):
        log.info(f'Downloading {self.filename}')
        playlist = stream or self.m3u_normalized()
        path = Path(out) / self.filename
        if path.exists():
            overwrite = input(f'{path} already exists. Overwrite? ')
            if not overwrite or overwrite.lower()[0] != 'y':
                return
        proc = await asyncio.create_subprocess_exec(
            'ffmpeg', *['-y', '-protocol_whitelist', 'file,http,https,tcp,tls,pipe', '-i', 'pipe:',
                        '-c', 'copy', '-bsf:a', 'aac_adtstoasc', '-f', 'mp4', str(path)],
            stdin=subprocess.PIPE,
        )
        proc.stdin.write(playlist.dumps().encode())
        proc.stdin.close()
        await proc.stdin.drain()
        await proc.wait()
        log.info(f'Finished downloading {self.filename}')

    def dump(self, output: Path):
        info_path = output / self.filename_info
        log.info(f'Dumping info to {info_path}')
        info = {**self.info}
        if self.m3u:
            info['_m3u'] = {
                'uri': self.best_stream,
                'content': self.m3u.dumps(),
            }
        with open(info_path, 'w+') as f:
            json.dump(info, f)

    @staticmethod
    def get_info(url: str) -> JSONDict:
        log.info(f'Extracting info from {url}')
        return ytdl.extract_info(url, download=False)


class TwitchStream(HLS):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chat = {
            'url': self.url,
            'comments': [],
        }

    @property
    def filename_chat(self) -> Path:
        return self.filename.with_suffix('.chat.json')

    @property
    def is_trimmed(self):
        if self.m3u is None:
            return None
        return (RE_TRIMMED_SEG.search(self.m3u.segments[0].uri) is not None
                or RE_TRIMMED_SEG.search(self.m3u.segments[1].uri) is not None)

    @property
    def chat_url(self) -> Optional[str]:
        chat = self.info.get('subtitles', {}).get('rechat')
        if not chat:
            return None
        return chat[0]['url']

    def m3u_normalized(self, extended=True) -> m3u8.M3U8:
        normalized = super().m3u_normalized()
        if not extended:
            return normalized
        for seg in normalized.segments:
            seg: m3u8.Segment
            trimmed = RE_TRIMMED_SEG.search(seg.uri)
            if trimmed:
                name = f'{trimmed.group(1)}.ts'
                seg.uri = url_path_op(seg.absolute_uri, Path.with_name, name)
                seg.duration = normalized.data['targetduration']
        return normalized

    def scan_for_muted(self):
        muted = {}
        time = 0
        for seg in self.m3u.segments:
            if 'muted' in seg.uri:
                muted[seg.uri] = time
            time += seg.duration
        m3u_dict = self.info.setdefault('_m3u', {})
        m3u_dict['muted'] = muted

    async def load_stream(self, extended=False, out='.'):
        playlist = self.m3u_normalized(extended)
        await super().load_stream(out, playlist)

    async def load_chat(self):
        log.info(f'Downloading chat replay for {self.url}')
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
        self.chat['comments'] = comments

    def dump(self, output: Path):
        super().dump(output)
        if self.chat['comments']:
            with open(output / self.filename_chat, 'w+') as f:
                json.dump(self.chat, f)
