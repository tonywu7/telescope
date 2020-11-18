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

import aiojobs
from aiohttp import web

from .urlkit import URLParam
from .twitch import TwitchApp


class TwitchServer(web.Application):
    def __init__(self, *args, logger=None, **kwargs):
        logger = logger or logging.getLogger('twitch_server')
        super().__init__(*args, logger=logger, **kwargs)

        self.twitch: TwitchApp = None
        self.add_routes([
            web.get('/server/test', self._debug_endpoint),
        ])
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

        self.submanager = SubscriptionManager(self)

        self.on_startup.append(self.submanager.create_scheduler)
        self.on_startup.append(TwitchServer.start_client)
        self.on_cleanup.append(self.submanager.close)
        self.on_cleanup.append(TwitchServer.close)

    def _url_for(self, endpoint, **kwargs):
        return f'{self["SERVER_ORIGIN"]}{self.router[endpoint].url_for(**kwargs)}'

    async def _debug_endpoint(self, req: web.Request):
        async with self.twitch._session.get('https://httpbin.org/ip') as res:
            return web.Response(body=await res.text(), content_type='application/json')

    async def start_client(self):
        app = TwitchApp(self['CLIENT_ID'], self['CLIENT_SECRET'])
        await app.authenticate()
        self.twitch = app

    async def list_subscriptions(self):
        async with self.twitch.request('/webhooks/subscriptions') as res:
            return await res.json()

    async def verify_stream_change_sub(self, req: web.Request):
        if 'hub.topic' not in req.query:
            return web.Response(status=444)

        user_id = req.match_info['user_id']
        challenge = req.query.get('hub.challenge')
        if not challenge:
            reason = req.query.get('hub.reason')
            self.logger.error(f'Subscription to stream change event for {user_id} denied.')
            self.logger.error(f'Reason: {reason}')
            return web.Response(status=204)

        self.logger.info(f'Subscription to stream change event for {user_id} verified')

        record = {k: req.query[k] for k in ('hub.lease_seconds', 'hub.topic')}
        if user_id not in self.twitch.users:
            await self.twitch.get_users(user_ids=[user_id])
        await self.submanager.add(user_id, f'{self["SERVER_ORIGIN"]}{req.path}', record)

        return web.Response(body=challenge, content_type='text/plain')

    async def handle_stream_change(self, req: web.Request):
        self.logger.info(req.url)
        self.logger.info(req.headers)
        self.logger.info(req.query)
        return web.Response()

    async def _subscribe(self, topic: str, callback: str, query: dict, lease: int = 86400):
        topic = URLParam(query).update_url(topic)
        payload = {
            'hub.callback': callback,
            'hub.mode': 'subscribe',
            'hub.topic': topic,
            'hub.lease_seconds': lease,
            'hub.secret': self['SECRET_KEY'],
        }
        async with self.twitch.request('/webhooks/hub', method='POST', data=payload) as res:
            if res.status != 202:
                raise ValueError(res)
        return {**query, **payload}

    async def subscribe_to_stream(self, user_id: str):
        self.logger.info(f'Subscribing to {user_id}')
        topic = 'https://api.twitch.tv/helix/streams'
        callback = self._url_for('sub-stream-changed-post', user_id=user_id)
        return await self._subscribe(topic, callback, {'user_id': user_id})

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


class SubscriptionManager:
    def __init__(self, server: TwitchServer):
        self.log = logging.getLogger('submanager')
        self.server = server
        self.scheduler: aiojobs.Scheduler = None
        self._subscriptions = {}

    async def create_scheduler(self, *args, **kwargs):
        self.scheduler = await aiojobs.create_scheduler()

    async def add(self, key, callback, info, autorenew=True):
        self.log.info(f'Added subscription {key} {info}')
        self._subscriptions[key] = info
        if autorenew:
            kwargs = {
                'topic': info['hub.topic'],
                'callback': callback,
                'query': {},
            }
            renew_after = int(info['hub.lease_seconds'])
            await self.scheduler.spawn(self.resubscribe(renew_after, **kwargs))

    async def close(self):
        await self.scheduler.close()

    async def resubscribe(self, after: int, *args, **kwargs):
        self.log.info(f'Subscription scheduled to renew after {after} seconds')
        await asyncio.sleep(int(after) * .9)
        self.log.info('Renewing subscription')
        await self.server._subscribe(*args, **kwargs)
