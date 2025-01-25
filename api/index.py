#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""This example showcases how PTBs "arbitrary callback data" feature can be used.

For detailed info on arbitrary callback data, see the wiki page at
https://github.com/python-telegram-bot/python-telegram-bot/wiki/Arbitrary-callback_data

Note:
To use arbitrary callback data, you must install PTB via
`pip install "python-telegram-bot[callback-data]"`
"""
import asyncio
import logging
import traceback
from datetime import datetime, timezone, timedelta
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from cozepy import (
    Coze, TokenAuth, Message, ChatEventType, COZE_CN_BASE_URL
)
from telegram.request import HTTPXRequest
from functools import wraps  # 添加装饰器所需的导入
import sys
import nest_asyncio
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn

from api.superbase_client import (get_or_create_user, get_user_daily_limit,
    get_today_usage_count, create_project, update_project_messages, get_user_membership_info
)
from api.config import TG_BOT_TOKEN, COZE_TOKEN, COZE_BOT_ID

# 配置日志输出到 stdout，这样 Vercel 可以捕获日志
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Coze API 配置
coze = Coze(
    auth=TokenAuth(token=COZE_TOKEN),
    base_url=COZE_CN_BASE_URL
)
BOT_ID = COZE_BOT_ID

# 自定义请求处理器配置
http_request = HTTPXRequest(
    connection_pool_size=16,  # Increased pool size for better concurrent handling
    connect_timeout=20.0,     # More generous timeout for connections
    read_timeout=20.0,        # More generous timeout for reading
    write_timeout=20.0,       # More generous timeout for writing
    pool_timeout=5.0,         # Increased pool timeout               # Add retry attempts for failed requests
)

# 初始化 bot 时使用自定义的请求处理器
bot = Bot(TG_BOT_TOKEN, request=http_request)
application = Application.builder().bot(bot).build()

# 应用 nest_asyncio 来允许嵌套的事件循环
nest_asyncio.apply()

def run_async(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(f(*args, **kwargs))
    return wrapper

async def initialize_user_data(context: ContextTypes.DEFAULT_TYPE, tg_user_id: str, user_name: str) -> None:
    """初始化或更新用户数据"""
    # 获取北京时间
    beijing_tz = timezone(timedelta(hours=8))
    current_date = datetime.now(beijing_tz).date()

    # 获取用户信息
    user = await get_or_create_user(tg_user_id, user_name)
    if not user:
        logger.error(f"Failed to get or create user for tg_user_id: {tg_user_id}")
        return

    # 获取用户每日限制和已使用次数
    daily_limit = await get_user_daily_limit(user['user_id'])
    used_count = await get_today_usage_count(user['user_id'])

    context.user_data['daily_limit'] = daily_limit
    context.user_data['daily_count'] = daily_limit - used_count
    context.user_data['last_date'] = current_date.isoformat()
    context.user_data['user_id'] = user['user_id']  # 存储用户ID而不是整个用户对象

# 添加一个简单的日志装饰器
def log_function(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        print(f"Starting {func.__name__}")  # Vercel 会捕获 print 语句
        try:
            result = await func(*args, **kwargs)
            print(f"Completed {func.__name__}")
            return result
        except Exception as e:
            print(f"Error in {func.__name__}: {str(e)}")
            raise
    return wrapper

@log_function
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """开始算卦流程"""
    try:
        chat_id = update.effective_chat.id
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name + " " + update.effective_user.last_name

        # 直接调用异步函数
        await initialize_user_data(context, user_id, user_name)

        if context.user_data.get('daily_count', 0) <= 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="今日算卦次数已用完，请明日再来。"
            )
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text="请输入你所求之事："
        )
        context.user_data['waiting_for_question'] = True

    except Exception as e:
        logger.error(f"Error in start: {e!r}")
        logger.error(traceback.format_exc())
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="系统出现错误，请稍后重试。"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理用户输入的问题"""
    if context.user_data.get('waiting_for_question'):
        await initialize_user_data(context, str(update.effective_user.id), 
                                 update.effective_user.first_name + " " + update.effective_user.last_name)

        if context.user_data['daily_count'] <= 0:
            await update.message.reply_text("今日算卦次数已用完，请明日再来。")
            return

        question = update.message.text
        context.user_data['waiting_for_question'] = False

        # 创建新的项目记录
        user_id = context.user_data['user_id']
        project = await create_project(user_id, question)
        if not project:
            await update.message.reply_text("系统错误，请稍后再试。")
            return

        messages = []
        text_buffer = ""
        message = None
        content_buffer = ""
        BUFFER_SIZE = 30

        try:
            user_id = project['project_id']
            for event in coze.chat.stream(
                bot_id=BOT_ID,
                user_id=user_id,
                additional_messages=[
                    Message.build_user_question_text(question),
                ],
            ):
                if event.event == ChatEventType.CONVERSATION_MESSAGE_DELTA:
                    content = event.message.content
                    if content.startswith("![") and "](" in content and content.endswith(")"):
                        img_url = content.split("](")[1][:-1]
                        await update.message.reply_photo(img_url)
                        messages.append({'role': 'assistant', 'content': content})
                    elif content.startswith("开始起卦"):
                        await update.message.reply_text("开始起卦")
                        messages.append({'role': 'assistant', 'content': content})
                    else:
                        content_buffer += content

                        if message is None:
                            message = await update.message.reply_text(
                                f"您所问的事：{question}\n\n卦象解析：\n{content_buffer}"
                            )
                            text_buffer = f"您所问的事：{question}\n\n卦象解析：\n{content_buffer}"
                            content_buffer = ""
                        elif len(content_buffer) >= BUFFER_SIZE:
                            text_buffer += content_buffer
                            formatted_text = text_buffer.replace("<br><br>", "\n")
                            try:
                                await message.edit_text(formatted_text)
                            except Exception as e:
                                logger.warning(f"Failed to update message: {str(e)}")
                            content_buffer = ""

            if content_buffer and message:
                text_buffer += content_buffer
                messages.append({'role': 'assistant', 'content': text_buffer})
                try:
                    await message.edit_text(text_buffer)
                    await update_project_messages(project['project_id'], messages)
                except Exception as e:
                    logger.warning(f"Failed to update final message: {str(e)}")

        except Exception as e:
            logger.error(f"算卦出错: {str(e)}")
            await update.message.reply_text("抱歉，算卦系统暂时遇到问题，请稍后再试。")
    else:
        await update.message.reply_text("请先发送 /start 开始算卦流程。")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """显示用户资料和今日剩余算卦次数"""
    await initialize_user_data(context, str(update.effective_user.id), update.effective_user.first_name + " " + update.effective_user.last_name)

    user_name = update.effective_user.first_name
    daily_count = context.user_data['daily_count']
    daily_limit = context.user_data['daily_limit']

    # 获取会员信息
    membership_info = await get_user_membership_info(context.user_data['user_id'])

    if membership_info:
        # 转换时间为北京时间
        beijing_tz = timezone(timedelta(hours=8))
        start_time = datetime.fromisoformat(membership_info['start_time']).astimezone(beijing_tz)
        end_time = datetime.fromisoformat(membership_info['end_time']).astimezone(beijing_tz)

        await update.message.reply_text(
            f"用户：{user_name}\n"
            f"会员等级：{membership_info['tier_name']}\n"
            f"会员说明：{membership_info['description']}\n"
            f"会员有效期：{start_time.strftime('%Y-%m-%d')} 至 {end_time.strftime('%Y-%m-%d')}\n"
            f"今日剩余算卦次数：{daily_count}\n"
            f"每日限额：{daily_limit}次"
        )
    else:
        await update.message.reply_text(
            f"用户：{user_name}\n"
            f"会员等级：免费用户\n"
            f"今日剩余算卦次数：{daily_count}\n"
            f"每日限额：{daily_limit}次"
        )

def suangua(question: str) -> str:
    """调用 Coze API 进行算卦"""
    logger.info(f"算卦问题：{question}")
    result = ""
    try:
        user_id = f"user_{hash(question)}"

        for event in coze.chat.stream(
            bot_id=BOT_ID,
            user_id=user_id,
            additional_messages=[
                Message.build_user_question_text(
                    f"{question}\n"
                ),
            ],
        ):
            print(f"收到事件：{event.event}")
            if event.event == ChatEventType.CONVERSATION_MESSAGE_DELTA:
                result += event.message.content
                print(f"收到消息：{event.message.content}")
            if event.event == ChatEventType.CONVERSATION_CHAT_COMPLETED:
                print(f"Token usage: {event.chat.usage.token_count}")

        # 确保所有特殊字符都被正确转义
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            result = result.replace(char, f'\\{char}')

        return result if result else "抱歉，算卦失败，请稍后再试。"

    except Exception as e:
        logger.error(f"算卦出错: {str(e)}")
        return "抱歉，算卦系统暂时遇到问题，请稍后再试。"

# 创建 FastAPI 应用
app = FastAPI()

# 全局变量来存储初始化状态
application = None
bot = None

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    global application, bot

    # 初始化 bot 和 application
    bot = Bot(TG_BOT_TOKEN, request=http_request)
    application = Application.builder().bot(bot).build()
    
    # 初始化 application
    await application.initialize()
    
    # 添加处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # 设置 webhook
    await application.bot.set_webhook(url="https://liuyao-bot.vercel.app/webhook")
    logger.info("Application initialized and webhook set")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    global application
    if application:
        await application.shutdown()
        logger.info("Application shut down")

@app.post("/webhook")
async def webhook(request: Request):
    """处理 Telegram webhook 请求"""
    try:
        if not application:
            raise RuntimeError("Application not initialized")
            
        json_data = await request.json()
        update = Update.de_json(json_data, application.bot)
        
        # 使用 application 的上下文管理器来处理更新
        async with application:
            await application.process_update(update)
            
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error in webhook: {e!r}")
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )

@app.get("/")
async def index():
    """首页"""
    return {"message": "Hello, this is the Telegram bot webhook!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)