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

from pkgutil import iter_modules
from typing import Generator, List


def iter_module_tree(pkg: str, parts: List[str] = None, depth: int = 1) -> Generator[List[str], None, None]:
    if not depth:
        return
    parts = parts or []
    for modinfo in iter_modules([pkg]):
        path = [*parts, modinfo.name]
        yield path
        if modinfo.ispkg:
            yield from iter_module_tree(f'{pkg}/{modinfo.name}', path, depth=depth - 1)
