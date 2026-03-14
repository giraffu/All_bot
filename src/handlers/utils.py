from telegram import Update
from telegram.ext import ContextTypes

def _is_mentioned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    msg = update.message
    chat = update.effective_chat
    
    if chat.type not in ['group', 'supergroup']:
        return True
        
    bot_username = context.bot.username
    
    # 1. Reply check
    if msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id:
        return True
        
    # 2. Mention check (Caption or Text)
    entities = msg.caption_entities if msg.caption else msg.entities
    if entities:
        text_content = msg.caption if msg.caption else msg.text
        for entity in entities:
            if entity.type == "mention":
                text = text_content[entity.offset:entity.offset + entity.length]
                if text.lower() == f"@{bot_username.lower()}":
                    return True
    return False

class MockMessage:
    """Mock Message object for reuse in utility functions"""
    def __init__(self, bot, chat_id, message_id):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.chat = type('obj', (object,), {'id': chat_id})
    
    async def edit_text(self, text, **kwargs):
        return await self.bot.edit_message_text(
            chat_id=self.chat_id,
            message_id=self.message_id,
            text=text,
            **kwargs
        )
        
    async def delete(self):
        return await self.bot.delete_message(
            chat_id=self.chat_id,
            message_id=self.message_id
        )
    
    async def reply_text(self, text, **kwargs):
        return await self.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            **kwargs
        )
