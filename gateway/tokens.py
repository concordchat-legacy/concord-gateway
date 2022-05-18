# Copyright 2021 Concord, Inc.
# See LICENSE for more information.
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
