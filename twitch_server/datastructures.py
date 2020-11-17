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

from collections.abc import MutableMapping, MutableSequence, MutableSet
from importlib.util import module_from_spec, spec_from_file_location

import simplejson as json


def compose_mappings(*mappings):
    base = {}
    base.update(mappings[0])
    for m in mappings[1:]:
        for k, v in m.items():
            if k in base and type(base[k]) is type(v):
                if isinstance(v, MutableMapping):
                    base[k] = compose_mappings(base[k], v)
                elif isinstance(v, MutableSet):
                    base[k] |= v
                elif isinstance(v, MutableSequence):
                    base[k].extend(v)
                else:
                    base[k] = v
            else:
                base[k] = v
    return base


class Settings(dict):
    @classmethod
    def normalize(cls, settings):
        to_upper = {}
        for k, v in settings.items():
            if not k.isupper():
                to_upper[k] = v
        for k, v in to_upper.items():
            settings[k.upper()] = v
            del settings[k]

    @classmethod
    def from_json(cls, settings, path):
        with open(path) as f:
            cls.merge(settings, json.load(f))

    @classmethod
    def from_pyfile(cls, settings, path):
        spec = spec_from_file_location('twitch_server.instance', path)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.from_object(settings, mod)

    @classmethod
    def from_object(cls, settings, obj):
        keys = dir(obj)
        cls.merge(settings, {k: getattr(obj, k) for k in keys if k.isupper()})

    @classmethod
    def merge(cls, settings, other):
        d = compose_mappings(settings, other)
        settings.clear()
        settings.update(d)
