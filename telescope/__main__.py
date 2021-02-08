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

from importlib import import_module
from pathlib import Path

import click

from .util.datastructures import Settings
from .util.importutil import iter_module_tree
from .util.logger import config_logging

INSTANCE = Path(__file__).parent.with_name('instance')


@click.group()
@click.option('-i', '--profile', required=False, default=None)
@click.option('-l', '--logfile', default=None)
@click.option('-d', '--debug', default=False, is_flag=True)
@click.pass_context
def main(ctx, profile, logfile, debug):
    level = 10 if debug else 20
    config_logging(level=level, logfile=logfile)

    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug

    config = {}
    Settings.from_json(config, INSTANCE / 'secrets.json')
    Settings.from_pyfile(config, INSTANCE / 'settings.py')
    if profile:
        Settings.from_pyfile(config, INSTANCE / f'{profile}.py')
    ctx.obj['CONFIG'] = config


def find_commands():
    for path in iter_module_tree(str(Path(__file__).parent)):
        try:
            ctl = import_module(f'.{path[0]}.cli', __package__)
        except ModuleNotFoundError:
            continue
        cmd = getattr(ctl, 'COMMANDS', [])
        for c in cmd:
            main.add_command(c)


if __name__ == '__main__':
    find_commands()
    main(prog_name='python -m telescope')
