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
import os
import socket
from pathlib import Path

import click
from aiohttp import web

from . import _config_logging
from .datastructures import Settings
from .server import TwitchServer

INSTANCE = Path(__file__).parent.with_name('instance')


async def subscribe(server: TwitchServer):
    await server.start_client()
    await server.subscribe_to_all()
    await server.close()


@click.group()
@click.option('-l', '--logfile', default=None)
@click.option('-d', '--debug', default=False, is_flag=True)
@click.pass_context
def cli(ctx, logfile, debug):
    level = 10 if debug else 20
    _config_logging(level=level, logfile=logfile)

    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug

    server = TwitchServer()
    Settings.from_json(server, INSTANCE / 'secrets.json')
    Settings.from_pyfile(server, INSTANCE / 'settings.py')
    ctx.obj['SERVER'] = server


@cli.command()
@click.pass_context
def subscribe_to_all(ctx):
    asyncio.run(subscribe(ctx.obj['SERVER']))


@cli.command()
@click.option('-s', '--sock', required=True, type=click.Path(dir_okay=False))
@click.pass_context
def run_server(ctx, sock):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    os.unlink(sock)
    s.bind(sock)
    os.chmod(sock, 0o660)
    web.run_app(ctx.obj['SERVER'], sock=s)


if __name__ == '__main__':
    cli()
