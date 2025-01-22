# 绑定处理程序
from aiohttp.abc import Application
from telegram.ext import CommandHandler

from config import TG_BOT_TOKEN

application = Application.builder().token(TG_BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("profile", profile))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.on_event("startup")
async def startup():
    # 初始化时不再重复发送菜单按钮
    await application.initialize()
    await application.bot.set_webhook(url="https://telegram-bot-zeta-azure.vercel.app/webhook")

@app.on_event("shutdown")
async def shutdown():
    await application.stop()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, bot)
        async with application:
            await application.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        print(f"Error processing update: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/send_photo")
async def send_photo(chat_id: str, photo_url: str):
    try:
        async with bot:  # 添加这个上下文管理器
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_url
            )
        return {"status": "success", "message": "Photo sent successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
async def index():
    return {"message": "Hello, this is the Telegram bot webhook!"}