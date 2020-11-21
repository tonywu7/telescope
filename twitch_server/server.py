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

import hmac
import logging
from operator import itemgetter

import simplejson as json
from aiohttp import web
from aiohttp_remotes import XForwardedRelaxed, setup

from .subscription import SubscriptionManager
from .twitch import TwitchApp
from .util import colored as _


class TwitchServer(web.Application):
    STREAM_CHANGE_NOTIF = itemgetter('user_id', 'user_name')

    def __init__(self, config, *args, logger=None, **kwargs):
        logger = logger or logging.getLogger('twitch_server')
        super().__init__(*args, logger=logger, **kwargs)

        self.update(config)
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

        self.twitch: TwitchApp = None
        self.submanager: SubscriptionManager = None
        self.notifications = {}

        self.on_startup.append(self.init)
        self.on_startup.append(self.startup)
        self.on_cleanup.append(self.close)

    async def init(self, *args, **kwargs):
        await setup(self, XForwardedRelaxed())
        self.twitch = TwitchApp(self)
        self.submanager = SubscriptionManager(self, self.twitch, self.router)
        await self.twitch.authenticate()
        await self.submanager.create_scheduler()

    async def startup(self, *args, **kwargs):
        await self.submanager.subscribe_to_all()

    async def _debug_endpoint(self, req: web.Request):
        return web.Response(body=req.remote)

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
        await self.submanager.register(user_id, f'{self["SERVER_ORIGIN"]}{req.path}', record)

        return web.Response(body=challenge, content_type='text/plain')

    async def handle_stream_change(self, req: web.Request):
        sig = req.headers.get('X-Hub-Signature')
        msg_id = req.headers.get('Twitch-Notification-Id')

        if not sig or not msg_id:
            return web.Response(status=444)
        if req.content_length > 1048576:
            return web.Response(status=413)

        if msg_id in self.notifications:
            return web.Response(status=204)

        msg = await req.read()
        digest, match = self.verify_signature(msg, sig[7:])
        if not match:
            self.logger.warn(f'Message signature {sig} does not match expected value {digest}')
            return web.Response(status=403)

        self.notifications[msg_id] = True
        data = json.loads(msg.decode('utf8'))['data']
        if not data:
            self.logger.info(f'User {req.match_info["user_id"]} goes offline.')
            return web.Response(status=204)
        data = data[0]

        user_id, user_name = self.STREAM_CHANGE_NOTIF(data)
        self.logger.info(_(f'{user_name} is live!', color='green', attrs=['bold']))

        handlers = self['SUBSCRIPTIONS']
        handler = handlers.get(('id', user_id), handlers.get(('login', user_name)))

        if not handlers:
            self.logger.warn(f'No handler for user {user_name} ({user_id})')
            return web.Response(status=204)

        try:
            await handler(req, data, self)
        except Exception as e:
            self.logger.error('Error while handling notification:')
            self.logger.error(f'Handler: {handler}')
            self.logger.error(f'Notification: {data}')
            self.logger.error('Exception', exc_info=e)

        return web.Response(status=204)

    async def close(self, *args, **kwargs):
        await self.twitch.close()
        await self.submanager.close()

    def verify_signature(self, data: bytes, sig: str):
        hash_ = hmac.new(self['SECRET_KEY'].encode('utf8'), data, 'sha256')
        digest = hash_.hexdigest()
        return digest, hmac.compare_digest(digest, sig)
