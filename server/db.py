import os
import datetime
import dotenv
from typing import Any
from cassandra.cqlengine import connection, models, columns, usertype, management
from cassandra.auth import PlainTextAuthProvider

dotenv.load_dotenv()

cloud = {'secure_connect_bundle': os.getcwd() + '\\server\\static\\bundle.zip'}
auth_provider = PlainTextAuthProvider(
    os.getenv('client_id'), os.getenv('client_secret')
)


def connect():
    try:
        connection.setup(
            [],
            'concord',
            cloud=cloud,
            auth_provider=auth_provider,
            metrics_enabled=True,
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


def _get_date():
    return datetime.datetime.now(datetime.timezone.utc)


class SettingsType(usertype.UserType):
    accept_friend_requests = columns.Boolean()
    accept_direct_messages = columns.Boolean()


class User(models.Model):
    __table_name__ = 'users'
    id = columns.BigInt(primary_key=True, partition_key=False)
    username = columns.Text(max_length=40)
    discriminator = columns.Integer(index=True)
    email = columns.Text(max_length=100)
    password = columns.Text()
    flags = columns.Integer()
    avatar = columns.Text(default='')
    banner = columns.Text(default='')
    locale = columns.Text(default='EN_US')
    joined_at = columns.DateTime(default=_get_date)
    bio = columns.Text(max_length=4000)
    settings = columns.UserDefinedType(SettingsType)
    verified = columns.Boolean(default=False)
    system = columns.Boolean(default=False)
    early_supporter_benefiter = columns.Boolean(default=True)
    bot = columns.Boolean(default=False)


class Role(usertype.UserType):
    id = columns.BigInt()
    name = columns.Text(max_length=100)
    color = columns.Integer()
    hoist = columns.Boolean()
    icon = columns.Text()
    position = columns.Integer()
    permissions = columns.BigInt()
    mentionable = columns.Boolean()


class Guild(models.Model):
    __table_name__ = 'guilds'
    id = columns.BigInt(primary_key=True, partition_key=True)
    name = columns.Text(max_length=40)
    description = columns.Text(max_length=4000)
    vanity_url = columns.Text(default='')
    icon = columns.Text(default='')
    banner = columns.Text(default='')
    owner_id = columns.BigInt(primary_key=True)
    nsfw = columns.Boolean(default=False)
    large = columns.Boolean(primary_key=True, default=False)
    perferred_locale = columns.Text(default='EN_US/EU')
    permissions = columns.BigInt()
    splash = columns.Text(default='')
    roles = columns.Set(columns.UserDefinedType(Role))
    features = columns.Set(columns.Text)


class UserType(usertype.UserType):
    id = columns.BigInt()
    username = columns.Text()
    discriminator = columns.Integer()
    email = columns.Text()
    password = columns.Text()
    flags = columns.Integer()
    avatar = columns.Text()
    banner = columns.Text()
    locale = columns.Text()
    joined_at = columns.DateTime()
    bio = columns.Text()
    settings = columns.UserDefinedType(SettingsType)
    verified = columns.Boolean()
    system = columns.Boolean()
    early_supporter_benefiter = columns.Boolean()
    bot = columns.Boolean(default=False)


class Member(models.Model):
    __table_name__ = 'members'
    id = columns.BigInt(primary_key=True, partition_key=True)
    guild_id = columns.BigInt(primary_key=True)
    user = columns.UserDefinedType(UserType)
    avatar = columns.Text(default='')
    banner = columns.Text(default='')
    joined_at = columns.DateTime(default=_get_date)
    roles = columns.List(columns.BigInt)
    nick = columns.Text(default='')


class PermissionOverWrites(usertype.UserType):
    id = columns.BigInt()
    type = columns.Integer(default=0)
    allow = columns.BigInt()
    deny = columns.BigInt()


class Channel(models.Model):
    __table_name__ = 'channels'
    id = columns.BigInt(primary_key=True, partition_key=True)
    guild_id = columns.BigInt(primary_key=True)
    type = columns.Integer(default=0)
    position = columns.Integer()
    permission_overwrites = columns.UserDefinedType(PermissionOverWrites)
    name = columns.Text(max_length=30)
    topic = columns.Text(max_length=1024)
    slowmode_timeout = columns.Integer()
    recipients = columns.List(columns.UserDefinedType(UserType))
    owner_id = columns.BigInt()
    parent_id = columns.BigInt()
    # NOTE: Store empty buckets to make sure we never go over them
    # NOTE: Maybe store this somewhere else? this could impact read perf
    empty_buckets = columns.Set(columns.Integer)


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
