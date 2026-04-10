import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Started FSM. Send photo.")
    return 1

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photo received. END.")
    return ConversationHandler.END

async def catch_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Caught by global text handler!")

async def main():
    app = Application.builder().token("123").build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            1: [MessageHandler(filters.PHOTO, receive_photo)]
        },
        fallbacks=[]
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT, catch_text))
    print("Test ready")

if __name__ == "__main__":
    asyncio.run(main())
