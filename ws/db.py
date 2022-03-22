import asyncio
import motor.core as motor
import motor.motor_asyncio as motor_
import dotenv
import os

dotenv.load_dotenv()

loop = asyncio.new_event_loop()
client: motor.AgnosticClient = motor_.AsyncIOMotorClient(
    os.getenv('mongo_uri'),
    io_loop=loop
)

_users: motor.AgnosticDatabase = client.get_database('users')

users: motor.AgnosticCollection = _users.get_collection('core')
