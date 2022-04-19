import os
import datetime
import dotenv
from typing import Any
from cassandra.cqlengine import connection, models, columns, usertype, management
from cassandra.auth import PlainTextAuthProvider

dotenv.load_dotenv()
auth_provider = PlainTextAuthProvider(
    os.getenv('client_id'), os.getenv('client_secret')
)


def connect():
    try:
        if os.getenv('safe', 'false') == 'true':
            cloud = {'secure_connect_bundle': os.getcwd() + '\\server\\static\\bundle.zip'}
            connection.setup(
                [],
                'concord',
                cloud=cloud,
                auth_provider=auth_provider,
                connect_timeout=200,
            )
        else:
            connection.setup(
                [],
                'concord',
                auth_provider=auth_provider,
                connect_timeout=200,
            )
    except:
        connect()


class Button(usertype.UserType):
    label = columns.Text()
    url = columns.Text()


class Activity(usertype.UserType):
    name = columns.Text()
    type = columns.Integer()
    url = columns.Text(default=None)
    created_at = columns.DateTime()
    emoji = columns.Text()
    buttons = columns.List(columns.UserDefinedType(Button))


class Presence(models.Model):
    __options__ = {'gc_grace_seconds': 86400}
    id = columns.BigInt(primary_key=True)
    since = columns.Integer(default=None)
    activity = columns.UserDefinedType(Activity)
    status = columns.Text(default='offline')
    afk = columns.Boolean(default=False)
    no_online = columns.Boolean(default=False)


def to_dict(model: models.Model) -> dict:
    initial: dict[str, Any] = model.items()
    ret = dict(initial)

    for name, value in initial:
        if isinstance(
            value,
            (
                usertype.UserType,
                models.Model
            )):
            # things like member objects or embeds can have usertypes 3/4 times deep
            # there shouldnt be a recursion problem though
            value = dict(value.items())
            for k, v in value.items():
                if isinstance(v, usertype.UserType):
                    value[k] = to_dict(v)
            ret[name] = value

        # some values are lists of usertypes
        elif isinstance(value, (list, set)):
            if isinstance(value, set):
                value = list(value)

            set_values = []

            for v in value:
                if isinstance(v, usertype.UserType):
                    set_values.append(to_dict(v.items()))
                else:
                    set_values.append(v)
            
            ret[name] = set_values

        if name == 'id' or name.endswith('_id') and len(str(value)) > 14:
            ret[name] = str(value)
        if name == 'permissions':
            ret[name] = str(value)

    return ret


if __name__ == '__main__':
    connect()
    management.sync_table(Presence)
    management.sync_type('concord', Activity)
    management.sync_type('concord', Button)
