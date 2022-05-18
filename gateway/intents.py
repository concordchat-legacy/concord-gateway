# Copyright 2021 Concord, Inc.
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
import functools


def _has_intent(v: int, i: int):
    return True if v & i else False


class Intents:
    def __init__(self, session_intents: int):
        has = functools.partial(_has_intent, session_intents)
        self.direct_messages = has(1 << 0)
        self.presences = has(1 << 1)
        self.guilds = has(1 << 2)
        self.guild_channels = has(1 << 3)
        self.guild_members = has(1 << 4)
        self.guild_messages = has(1 << 5)

if __name__ == '__main__':
    print(1 << 1 | 1 << 2)
