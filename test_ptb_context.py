import asyncio
from telegram.ext import CallbackContext, Application
from telegram import Update

async def main():
    app = Application.builder().token("123:ABC").build()
    context = CallbackContext(app)
    try:
        context.lang = "en"
        print("Success: context.lang =", context.lang)
    except Exception as e:
        print("Error:", type(e).__name__, e)

asyncio.run(main())
