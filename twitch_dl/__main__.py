import asyncio
from pathlib import Path

import click
import simplejson as json

from . import _config_logging
from .session import close_session, init
from .stream import TwitchStream


@click.group()
@click.option('-d', '--debug', default=False, is_flag=True)
def cli(debug):
    level = 10 if debug else 20
    _config_logging(level)


@cli.command()
@click.argument('url')
@click.option('-o', '--output', default='.', type=click.Path(exists=True, file_okay=False))
@click.option('-n', '--no-download', default=False, is_flag=True)
@click.option('-p', '--save-m3u8', default=False, is_flag=True)
@click.option('-c', '--chat', default=False, is_flag=True)
@click.option('-t', '--thumbnail', default=False, is_flag=True)
@click.option('-e', '--extended', default=False, is_flag=True)
def download(url, output, **kwargs):
    output = Path(output)
    asyncio.run(run_download(url, output, **kwargs))


@cli.command()
@click.argument('info')
@click.option('-o', '--output', default='.', type=click.Path(exists=True, file_okay=False))
@click.option('-n', '--no-download', default=False, is_flag=True)
@click.option('-p', '--save-m3u8', default=False, is_flag=True)
@click.option('-c', '--chat', default=False, is_flag=True)
@click.option('-t', '--thumbnail', default=False, is_flag=True)
@click.option('-e', '--extended', default=False, is_flag=True)
def load(info, output, **kwargs):
    output = Path(output)
    with open(info) as f:
        info = json.load(f)
    asyncio.run(run_load_info(info, output, **kwargs))


async def run_download(url, wd, *args, **kwargs):
    init(concurrency=32)
    try:
        video: TwitchStream = await TwitchStream.from_url(url)
        await common(video, wd, **kwargs)
        video.dump(wd)
    finally:
        await close_session()


async def run_load_info(info, wd, *args, **kwargs):
    init(concurrency=32)
    try:
        video: TwitchStream = TwitchStream(info)
        await video.load_m3u()
        await common(video, wd, **kwargs)
        video.dump(wd)
    finally:
        await close_session()


async def common(video: TwitchStream, wd,
                 chat=True, thumbnail=True,
                 extended=True, no_download=False,
                 save_m3u8=False):
    video.scan_for_muted()
    if chat:
        await video.load_chat()
    if thumbnail:
        await video.load_thumbnail(wd)
    if not no_download:
        await video.load_stream(extended, wd)
    if save_m3u8:
        video.m3u.dump(video.filename_m3u)
        video.m3u_normalized(extended).dump(video.filename_m3u_norm)


if __name__ == '__main__':
    cli()
