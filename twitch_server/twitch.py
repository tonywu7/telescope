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

import logging
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import aiohttp

from .urlkit import URLParam


class TwitchApp:
    def __init__(self, config, *args, **kwargs):
        self.config = config
        self.log = logging.getLogger('twitch')

        self._session = aiohttp.ClientSession()
        self._token: AccessToken = None

        self.users = {}

    def _helix_endpoint(self, endpoint: str, data=None):
        data = data or {}
        data = URLParam(data)
        query = f'?{data.query_string()}' if data else ''
        return f'https://api.twitch.tv/helix{endpoint}{query}'

    @property
    def access_token(self):
        if not self._token:
            raise ValueError('No token is currently available')
        if self._token.expired:
            raise ValueError('Current token has expired')
        return self._token.access

    async def close(self):
        await self.revoke()
        await self._session.close()

    async def authenticate(self):
        self.log.info('Obtaining an access token ...')
        async with self._session.post(
            url='https://id.twitch.tv/oauth2/token',
            data={
                'client_id': self.config['CLIENT_ID'],
                'client_secret': self.config['CLIENT_SECRET'],
                'grant_type': 'client_credentials',
            },
        ) as res:
            self._token = AccessToken(await res.json())
            self.log.info(f'New access token expires at {self._token.exp}')

    async def revoke(self):
        self.log.info('Revoking current access token ...')
        async with self._session.post(
            url='https://id.twitch.tv/oauth2/revoke',
            data={
                'client_id': self.config['CLIENT_ID'],
                'token': self.access_token,
            },
        ):
            self._token = None

    @asynccontextmanager
    async def request(self, endpoint: str, *, method='GET', data=None, query=True):
        self.log.debug(f'Fetching {endpoint} with HTTP {method}')

        endpoint = self._helix_endpoint(endpoint)
        if (method == 'GET' or query) and data:
            endpoint = URLParam(data).update_url(endpoint)
            data = None

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'client-id': self.config['CLIENT_ID'],
        }

        async with self._session.request(
            method=method, url=endpoint,
            json=data, headers=headers,
        ) as res:
            try:
                yield res
            finally:
                return

    async def _json_response(self, res: aiohttp.ClientResponse):
        if res.status == 401:
            raise ValueError('Twitch returned HTTP 401 Unauthorized')
        if res.status == 429:
            raise ValueError('Twitch returned HTTP 429 Too Many Requests')
        data = await res.json()
        if 'error' in data:
            raise ValueError(data)
        return data

    async def get_users(self, *, user_ids: Optional[List[int]] = None,
                        user_logins: Optional[List[str]] = None):
        if not user_ids and not user_logins:
            raise ValueError('Must supplie user IDs and/or usernames')
        user_ids = user_ids or []
        user_logins = user_logins or []
        params = URLParam()
        for k, ls in (('id', user_ids), ('login', user_logins)):
            for info in ls:
                params.add(k, info)
        async with self.request('/users', data=params) as res:
            data = (await self._json_response(res))['data']
            for user in data:
                self.users[user['id']] = user
            return data

    async def list_subscriptions(self):
        async with self.request('/webhooks/subscriptions') as res:
            return await res.json()


class AccessToken:
    def __init__(self, token):
        self.access = token['access_token']
        self.iat = time.time()
        self.exp = self.iat + token['expires_in']
        self.refresh = token.get('refresh_token')
        self.scopes = token.get('scopes')

    @property
    def expired(self):
        return time.time() > self.exp
