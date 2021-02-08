# MIT License
#
# Copyright (c) 2020 Tony Wu +https://github.com/tonywu7
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
from pathlib import Path

import click
from aiohttp import web

from ..util.sockets import get_socket
from .server import TwitchServer

INSTANCE = Path(__file__).parent.with_name('instance')


@click.group()
@click.pass_context
def server(ctx):
    server = TwitchServer(ctx.obj['CONFIG'])
    ctx.obj['SERVER'] = server


@server.command()
@click.option('-p', '--port', type=click.INT, default=8081)
@click.option('-s', '--sock', type=click.Path(dir_okay=False))
@click.pass_context
def run_server(ctx, port: 8081, sock=None):
    if sock:
        sock = get_socket(sock)
        port = None
    else:
        port = int(port)
    web.run_app(ctx.obj['SERVER'], port=port, sock=sock)


@server.command()
@click.pass_context
def subscribe_to_all(ctx):
    server: TwitchServer = ctx.obj['SERVER']

    async def main():
        await server.init()
        await server.close()

    asyncio.run(main())


@server.command()
@click.pass_context
def list_subscriptions(ctx):
    server: TwitchServer = ctx.obj['SERVER']

    async def main():
        await server.init(subscribe=False)
        server.logger.info(await server.twitch.list_subscriptions())
        await server.close()

    asyncio.run(main())


COMMANDS = [server]
