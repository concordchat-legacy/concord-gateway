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
import base64
import binascii
from typing import List

import itsdangerous
from cassandra.cluster import Session
from cassandra.cqlengine.connection import get_session


def verify_token(token: str):
    if token.startswith('ConcordBot '):
        token = token.replace('ConcordBot ', '')
    elif token.startswith('ConcordUser '):
        token = token.replace('ConcordUser ', '')

    fragmented = token.split('.')
    user_id = fragmented[0]

    try:
        user_id = base64.b64decode(user_id.encode())
        user_id = int(user_id)
    except (ValueError, binascii.Error):
        raise ValueError()

    session: Session = get_session()
    user: List[dict] = session.execute('SELECT * FROM users WHERE id = {};'.format(str(user_id)))

    if user == []:
        raise ValueError()

    user2 = user[0]

    signer = itsdangerous.TimestampSigner(user2['password'])

    try:
        signer.unsign(token)

        return user2
    except (itsdangerous.BadSignature):
        raise ValueError()
