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

import asyncio
import logging

from aiohttp import web

from .twitch import TwitchApp


class TwitchServer(web.Application):
    def __init__(self, *args, logger=None, **kwargs):
        logger = logger or logging.getLogger('twitch_server')
        super().__init__(*args, logger=logger, **kwargs)

        self.twitch: TwitchApp = None
        self.add_routes([
            web.get(
                '/twitch/webhook/stream_changed/{user_id}', self.verify_stream_change_sub,
                name='sub-stream-changed-get',
            ),
            web.post(
                '/twitch/webhook/stream_changed/{user_id}', self.handle_stream_change,
                name='sub-stream-changed-post',
            ),
        ])

    def _url_for(self, endpoint, **kwargs):
        return f'{self["SERVER_ORIGIN"]}{self.router[endpoint].url_for(**kwargs)}'

    async def start_client(self):
        app = TwitchApp(self['CLIENT_ID'], self['CLIENT_SECRET'])
        await app.authenticate()
        self.twitch = app

    async def verify_stream_change_sub(req: web.Request):
        log = logging.getLogger('webhook.streams')
        challenge = req.query.get('hub.challenge')
        if not challenge:
            reason = req.query.get('hub.reason')
            log.error(f'Subscription to stream change event for {req.match_info["user_id"]} denied.')
            log.error(f'Reason: {reason}')
            return web.Response(status=204)
        log.info(f'Subscription to stream change event for {req.match_info["user_id"]} verified')
        return web.Response(body=challenge, content_type='text/plain')

    async def handle_stream_change(req: web.Request):
        return web.Response()

    async def subscribe_to_stream(self, user_id: int):
        payload = {
            'hub.callback': self._url_for('sub-stream-changed-post', user_id=user_id),
            'hub.mode': 'subscribe',
            'hub.topic': 'https://api.twitch.tv/helix/streams',
            'hub.lease_seconds': 86400,
            'hub.secret': self['SECRET_KEY'],
        }

        async with self.twitch.request(
            'https://api.twitch.tv/helix/webhooks/hub',
            method='POST',
            data=payload,
        ) as res:
            if res.status != 202:
                raise ValueError(res)

        return {'user_id': user_id, **payload}

    async def subscribe_to_all(self):
        users = {'user_ids': [], 'user_logins': []}
        for k in self['SUBSCRIPTIONS']:
            id_type, info = k
            users[f'user_{id_type}s'].append(info)
        info = await self.twitch.get_users(**users)

        jobs = [self.subscribe_to_stream(d['id']) for d in info]
        results = await asyncio.gather(*jobs, return_exceptions=True)

        for payload in results:
            if isinstance(payload, Exception):
                self.logger.error(payload, exc_info=True)
            self.logger.info(f'Subscription to {payload["user_id"]} accepted.')

    async def close(self):
        await self.twitch.close()
