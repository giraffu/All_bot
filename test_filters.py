from telegram import Message, Chat, MessageEntity
from telegram.ext import filters
import datetime

msg = Message(
    message_id=1,
    date=datetime.datetime.now(),
    chat=Chat(id=1, type="private"),
    text="/cancel",
    entities=[MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=7)]
)
print("With entities:", filters.COMMAND(msg))

msg2 = Message(
    message_id=2,
    date=datetime.datetime.now(),
    chat=Chat(id=1, type="private"),
    text="/cancel"
)
print("Without entities:", filters.COMMAND(msg2))
