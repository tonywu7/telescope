# Copyright 2021 Tony Wu +https://github.com/tonywu7/
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hmac
import logging
from operator import itemgetter

import pendulum
import simplejson as json
from aiohttp import web
from aiohttp_remotes import XForwardedRelaxed, setup

from ..util.logger import colored as _
from .subscription import SubscriptionManager
from .twitch import TwitchApp


class TwitchServer(web.Application):
    STREAM_CHANGE_NOTIF = itemgetter('user_id', 'user_name')
    STREAM_CHANGE_INFO = itemgetter('title', 'game_id', 'viewer_count', 'started_at')

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
        self.on_cleanup.append(self.close)

        self.inprogress = {}

    async def init(self, subscribe=True, *args, **kwargs):
        await setup(self, XForwardedRelaxed())
        self.twitch = TwitchApp(self)
        self.submanager = SubscriptionManager(self, self.twitch, self.router)
        await self.twitch.authenticate()
        await self.submanager.create_scheduler()
        if subscribe:
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

        file_name = self['OUTPUT_PATH'] / f'{user_name}-{pendulum.now().strftime("%y%m%d.%H%M%S")}.json'
        with open(file_name, 'w+') as f:
            json.dump(data, f)

        try:
            title, game_id, viewer_count, started_at = self.STREAM_CHANGE_INFO(data)
            games = await self.twitch.get_games(game_ids=[game_id])
            if games:
                self.logger.info(_(f'{user_name} is playing {games[0]["name"]}', color='magenta', attrs=['bold']))
            self.logger.info(_(f'Streaming "{title}" with {viewer_count} viewers', color='magenta', attrs=['bold']))
            timestamp = pendulum.parse(started_at)
            pt = timestamp.in_timezone('America/Los_Angeles')
            et = timestamp.in_timezone('America/New_York')
            diff = pendulum.now().in_timezone('UTC') - timestamp
            self.logger.info(_(f'Stream started at {pt.to_time_string()} PT, {et.to_time_string()} ET', color='blue', attrs=['bold']))
            self.logger.info(_(f'({diff.as_interval().in_words()} ago)', color='blue', attrs=['bold']))
        except Exception:
            self.logger.debug('Failed to obtain stream details')

        handlers = self['SUBSCRIPTIONS']
        handler = handlers.get(('id', int(user_id)), handlers.get(('login', user_name.lower())))

        if not handlers:
            self.logger.warn(f'No handler for user {user_name} ({user_id})')
            return web.Response(status=204)

        stream_id = data['id']
        if stream_id in self.inprogress:
            self.logger.info(f'Stream {stream_id} has already started.')
            return web.Response(status=204)

        self.inprogress[stream_id] = data
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
