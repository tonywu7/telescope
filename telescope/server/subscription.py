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

import asyncio
import logging

import aiojobs
from aiohttp.web_urldispatcher import UrlDispatcher

from ..util.urlkit import URLParam
from .twitch import TwitchApp


class SubscriptionManager:
    def __init__(self, config, twitch: TwitchApp, router: UrlDispatcher):
        self.log = logging.getLogger('submanager')
        self.config = config
        self.twitch = twitch
        self.router = router
        self.scheduler: aiojobs.Scheduler = None
        self._subscriptions = {}

    def _url_for(self, endpoint, **kwargs):
        return f'{self.config["SERVER_ORIGIN"]}{self.router[endpoint].url_for(**kwargs)}'

    async def create_scheduler(self):
        self.scheduler = await aiojobs.create_scheduler()

    async def _subscribe(self, topic: str, callback: str, query: dict, lease: int = 86400):
        topic = URLParam(query).update_url(topic)
        payload = {
            'hub.callback': callback,
            'hub.mode': 'subscribe',
            'hub.topic': topic,
            'hub.lease_seconds': lease,
            'hub.secret': self.config['SECRET_KEY'],
        }
        async with self.twitch.request('/webhooks/hub', method='POST', data=payload) as res:
            if res.status != 202:
                raise ValueError(res)
        return {**query, **payload}

    async def subscribe_to_stream(self, user_id: str):
        self.log.info(f'Subscribing to {user_id}')
        topic = 'https://api.twitch.tv/helix/streams'
        callback = self._url_for('sub-stream-changed-post', user_id=user_id)
        return await self._subscribe(topic, callback, {'user_id': user_id})

    async def subscribe_to_all(self):
        users = {'user_ids': [], 'user_logins': []}
        for k in self.config['SUBSCRIPTIONS']:
            id_type, info = k
            users[f'user_{id_type}s'].append(info)
        info = await self.twitch.get_users(**users)

        jobs = [self.subscribe_to_stream(d['id']) for d in info]
        results = await asyncio.gather(*jobs, return_exceptions=True)

        for payload in results:
            if isinstance(payload, Exception):
                self.log.error(payload, exc_info=True)
            self.log.info(f'Subscription to {payload["user_id"]} accepted.')

    async def register(self, key, callback, info, autorenew=True):
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

    async def resubscribe(self, after: int, *args, **kwargs):
        self.log.info(f'Subscription scheduled to renew in {after} seconds')
        await asyncio.sleep(int(after) * .9)
        self.log.info('Renewing subscription')
        await self._subscribe(*args, **kwargs)

    async def close(self):
        await self.scheduler.close()
