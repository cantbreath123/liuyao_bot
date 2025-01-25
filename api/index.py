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
from datetime import datetime, timezone, timedelta
from typing import Callable, Any  # 添加必要的类型导入
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
import httpx
from functools import wraps  # 添加装饰器所需的导入

from api.superbase_client import (get_or_create_user, get_user_daily_limit,
    get_today_usage_count, create_project, update_project_messages, get_user_membership_info
)
from api.config import TG_BOT_TOKEN, COZE_TOKEN, COZE_BOT_ID
from flask import Flask, request, jsonify

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Coze API 配置
coze = Coze(
    auth=TokenAuth(token=COZE_TOKEN),
    base_url=COZE_CN_BASE_URL
)
BOT_ID = COZE_BOT_ID

# 自定义请求处理器，改名为 http_request
http_request = HTTPXRequest(
    connection_pool_size=8,
    connect_timeout=10.0,
    read_timeout=10.0,
    write_timeout=10.0,
    pool_timeout=3.0,
)

# 初始化 bot 时使用自定义的请求处理器
bot = Bot(TG_BOT_TOKEN, request=http_request)
application = Application.builder().bot(bot).build()

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

def with_error_handling(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                async with asyncio.timeout(10):  # 为每个操作设置超时
                    return await func(*args, **kwargs)
            except (asyncio.TimeoutError, telegram.error.TimedOut) as e:
                retry_count += 1
                logger.error(f"Timeout in {func.__name__}: {str(e)}")
                if retry_count >= max_retries:
                    raise
                await asyncio.sleep(1 * retry_count)  # 递增等待时间
            except Exception as e:
                retry_count += 1
                logger.error(f"Error in {func.__name__}: {str(e)}")
                if retry_count >= max_retries:
                    raise
                await asyncio.sleep(1)
                
    return wrapper

@with_error_handling
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """开始算卦流程"""
    try:
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name + " " + update.effective_user.last_name
        
        # 初始化用户数据
        logger.info(f"Starting divination for user: {user_id}")
        await initialize_user_data(context, user_id, user_name)
        
        # 检查是否还有剩余次数
        if context.user_data.get('daily_count', 0) <= 0:
            await update.message.reply_text("今日算卦次数已用完，请明日再来。")
            return

        # 使用 asyncio.shield 来保护关键操作
        await asyncio.shield(update.message.reply_text("请输入你所求之事："))
        context.user_data['waiting_for_question'] = True
        
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")
        try:
            await update.message.reply_text("系统出现错误，请稍后重试。")
        except Exception as reply_error:
            logger.error(f"Error sending error message: {str(reply_error)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理用户输入的问题"""
    if context.user_data.get('waiting_for_question'):
        await initialize_user_data(context, str(update.effective_user.id), update.effective_user.first_name + " " + update.effective_user.last_name)
        
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
            user_id = project['project_id']  # 使用项目ID作为会话ID
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
                            # 初始化消息
                            message = await update.message.reply_text(
                                f"您所问的事：{question}\n\n卦象解析：\n{content_buffer}"
                            )
                            text_buffer = f"您所问的事：{question}\n\n卦象解析：\n{content_buffer}"
                            content_buffer = ""  # 清空内容缓冲区
                        elif len(content_buffer) >= BUFFER_SIZE:
                            # 更新现有消息
                            text_buffer += content_buffer  # 将新内容添加到总缓冲区
                            formatted_text = text_buffer.replace("<br><br>", "\n")
                            try:
                                await message.edit_text(formatted_text)
                            except Exception as e:
                                logger.warning(f"Failed to update message: {str(e)}")
                            content_buffer = ""  # 清空内容缓冲区
            
            # 最后更新一次消息和项目记录
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

def create_app():
    app = Flask(__name__)
    
    def init_webhook():
        import asyncio
        async def setup():
            await application.initialize()
            await application.bot.set_webhook(url="https://liuyao-bot.vercel.app/webhook")
        asyncio.run(setup())
    
    init_webhook()
    
    @app.route("/webhook", methods=["POST"])
    def webhook():
        try:
            json_data = request.get_json()
            update = Update.de_json(json_data, bot)
            
            async def process_update():
                async with application:
                    await application.process_update(update)

            # 使用上下文管理器处理事件循环
            from contextlib import contextmanager

            @contextmanager
            def managed_event_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    yield loop
                finally:
                    try:
                        # 取消所有待处理的任务
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()
                        
                        # 运行一次以处理取消的任务
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                            
                        # 关闭事件循环
                        if not loop.is_closed():
                            loop.run_until_complete(loop.shutdown_asyncgens())
                            loop.close()
                    except Exception as e:
                        logger.error(f"Error cleaning up event loop: {str(e)}")
                    finally:
                        asyncio.set_event_loop(None)

            # 使用上下文管理器
            with managed_event_loop() as loop:
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(process_update(), timeout=30.0)
                    )
                except asyncio.TimeoutError:
                    logger.error("Request timeout")
                except Exception as e:
                    logger.error(f"Error in webhook: {str(e)}")
                    
            return jsonify({"status": "ok"})
            
        except Exception as e:
            logger.error(f"Error in webhook: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/send_photo", methods=["POST"])
    def send_photo():
        try:
            data = request.get_json()
            chat_id = data.get('chat_id')
            photo_url = data.get('photo_url')

            if not chat_id or not photo_url:
                return jsonify({"status": "error", "message": "Missing chat_id or photo_url"}), 400

            async def send():
                try:
                    async with bot:
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_url
                        )
                except Exception as e:
                    logger.error(f"Error sending photo: {str(e)}")

            # 使用新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(send())
            finally:
                loop.close()
                asyncio.set_event_loop(None)  # 清除当前事件循环
                
            return jsonify({"status": "success", "message": "Photo sent successfully"})
        except Exception as e:
            logger.error(f"Error in send_photo: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/")
    def index():
        return jsonify({"message": "Hello, this is the Telegram bot webhook!"})
        
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)