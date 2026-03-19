from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

async def send_payment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送带有 Mini App 按钮的支付菜单"""
    
    # 这里的 URL 必须是 HTTPS，并且需要在 BotFather -> /newapp 或 /editapp 中配置过
    # 这是您刚刚在 Cloudflare 上部署的真实域名
    mini_app_url = "https://pay.aivison.it.com" 
    
    keyboard = [
        [
            InlineKeyboardButton(
                text="💎 打开灵石充值中心",
                web_app=WebAppInfo(url=mini_app_url)
            )
        ],
        [
            InlineKeyboardButton(text="🔙 返回主菜单", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔮 **灵石充值**\n\n"
        "点击下方按钮打开充值中心，支持 TON 钱包一键支付。\n"
        "支付成功后，灵石将自动到账！",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
