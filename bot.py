#!/usr/bin/env python3
"""
Yonote Notifications Bot
Бот для получения уведомлений о комментариях из Yonote
"""

import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import pytz
import aiohttp
import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv не обязательна

from settings import NotificationSettings

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
YONOTE_API_BASE = "https://app.yonote.ru/api"
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
DB_PATH = "yonote_bot.db"

class YonoteAPI:
    """Класс для работы с API Yonote"""
    
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.session = None
    
    async def _get_session(self):
        """Получение HTTP сессии"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def _make_request(self, endpoint: str, data: dict = None) -> dict:
        """Выполнение запроса к API"""
        session = await self._get_session()
        url = f"{YONOTE_API_BASE}/{endpoint}"
        
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        try:
            async with session.post(url, json=data or {}, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"API request failed: {resp.status} - {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"API request error: {e}")
            return None
    
    async def get_auth_info(self) -> dict:
        """Получение информации об авторизации"""
        return await self._make_request("auth.info")
    
    async def get_events(self, limit: int = 50, offset: int = 0) -> dict:
        """Получение списка событий"""
        return await self._make_request("events.list", {
            "limit": limit,
            "offset": offset
        })
    
    async def get_document_info(self, document_id: str) -> dict:
        """Получение информации о документе"""
        return await self._make_request("documents.info", {
            "id": document_id
        })
    
    async def get_comments_list(self, document_id: str) -> dict:
        """Получение списка комментариев документа"""
        return await self._make_request("comments.list", {
            "entityId": document_id
        })
    
    async def close(self):
        """Закрытие сессии"""
        if self.session:
            await self.session.close()

class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    yonote_token TEXT,
                    notifications_enabled BOOLEAN DEFAULT 1,
                    last_event_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
    
    async def save_user_token(self, user_id: int, token: str):
        """Сохранение токена пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO users (user_id, yonote_token) 
                VALUES (?, ?)
            """, (user_id, token))
            await db.commit()
    
    async def get_user_token(self, user_id: int) -> Optional[str]:
        """Получение токена пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT yonote_token FROM users WHERE user_id = ?", 
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
    
    async def get_all_users(self) -> List[Dict]:
        """Получение всех пользователей"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id, yonote_token, notifications_enabled, last_event_id FROM users"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        'user_id': row[0],
                        'yonote_token': row[1],
                        'notifications_enabled': bool(row[2]),
                        'last_event_id': row[3]
                    }
                    for row in rows
                ]
    
    async def update_notifications_enabled(self, user_id: int, enabled: bool):
        """Обновление статуса уведомлений"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET notifications_enabled = ? WHERE user_id = ?
            """, (enabled, user_id))
            await db.commit()
    
    async def update_last_event_id(self, user_id: int, event_id: str):
        """Обновление ID последнего события"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET last_event_id = ? WHERE user_id = ?
            """, (event_id, user_id))
            await db.commit()
    
    async def delete_user(self, user_id: int):
        """Удаление пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            await db.commit()

class YonoteBot:
    """Основной класс Telegram бота"""
    
    def __init__(self):
        self.app = None
        self.db = Database()
        self.settings = NotificationSettings()
        self.scheduler = AsyncIOScheduler()
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id
        
        # Проверяем, есть ли уже токен у пользователя
        token = await self.db.get_user_token(user_id)
        
        if token:
            await update.message.reply_text(
                "👋 Привет! Ваше пространство Yonote уже подключено.\n\n"
                "Вы будете получать уведомления о комментариях на страницах, "
                "где вы являетесь автором или соавтором.",
                reply_markup=self._get_main_menu()
            )
        else:
            keyboard = [[InlineKeyboardButton("🔗 Подключить пространство", callback_data="connect")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "👋 Привет! Я бот для получения уведомлений из Yonote.\n\n"
                "Я буду уведомлять вас о событиях с комментариями:\n"
                "• Создание комментария\n"
                "• Изменение комментария\n"
                "• Удаление комментария\n"
                "• Изменение статуса комментария\n\n"
                "Уведомления приходят только для страниц, где вы являетесь "
                "автором или соавтором.",
                reply_markup=reply_markup
            )
    
    async def connect_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопки подключения"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "🔑 Для подключения вашего пространства Yonote:\n\n"
            "1. Перейдите на страницу настроек: https://app.yonote.ru/settings\n"
            "2. Найдите раздел 'API токены'\n"
            "3. Создайте новый токен или скопируйте существующий\n"
            "4. Отправьте токен в ответном сообщении\n\n"
            "⚠️ Токен будет удален из чата после подключения для безопасности."
        )
        
        # Устанавливаем состояние ожидания токена
        context.user_data['waiting_for_token'] = True
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        if context.user_data.get('waiting_for_token'):
            await self._handle_token_input(update, context)
        else:
            await update.message.reply_text(
                "Используйте меню для управления ботом.",
                reply_markup=self._get_main_menu()
            )
    
    async def _handle_token_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода токена"""
        token = update.message.text.strip()
        user_id = update.effective_user.id
        
        # Удаляем сообщение с токеном
        await update.message.delete()
        
        # Проверяем токен
        api = YonoteAPI(token)
        auth_info = await api.get_auth_info()
        
        if auth_info and auth_info.get('ok'):
            # Токен валидный, сохраняем
            await self.db.save_user_token(user_id, token)
            context.user_data['waiting_for_token'] = False
            
            # Удаляем все сообщения в чате (последние 20)
            try:
                for i in range(20):
                    try:
                        await context.bot.delete_message(
                            chat_id=update.effective_chat.id,
                            message_id=update.message.message_id - i
                        )
                    except:
                        pass
            except:
                pass
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="✅ Подключение выполнено успешно!\n\n"
                     "Теперь вы будете получать уведомления о комментариях из Yonote.",
                reply_markup=self._get_main_menu()
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Неверный токен. Пожалуйста, проверьте токен и попробуйте еще раз."
            )
        
        await api.close()
    
    async def settings_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопки настроек"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        notifications_enabled = await self.settings.are_notifications_enabled(user_id)
        
        keyboard = []
        
        if notifications_enabled:
            keyboard.append([InlineKeyboardButton("🔕 Отключить уведомления", callback_data="disable_notifications")])
        else:
            disabled_until = await self.settings.get_disabled_until(user_id)
            if disabled_until:
                time_left = disabled_until - datetime.now()
                hours_left = int(time_left.total_seconds() / 3600)
                minutes_left = int((time_left.total_seconds() % 3600) / 60)
                
                if hours_left > 0:
                    time_text = f"{hours_left}ч {minutes_left}м"
                else:
                    time_text = f"{minutes_left}м"
                
                keyboard.append([InlineKeyboardButton("🔔 Включить уведомления", callback_data="enable_notifications")])
                status_text = f"⚙️ Настройки бота:\n\n🔕 Уведомления отключены (осталось: {time_text})"
            else:
                keyboard.append([InlineKeyboardButton("🔔 Включить уведомления", callback_data="enable_notifications")])
                status_text = "⚙️ Настройки бота:\n\n🔕 Уведомления отключены"
        
        keyboard.extend([
            [InlineKeyboardButton("🔄 Сменить пространство", callback_data="change_workspace")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = "⚙️ Настройки бота:" if notifications_enabled else status_text
        
        await query.edit_message_text(
            message_text,
            reply_markup=reply_markup
        )
    
    async def disable_notifications_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отключение уведомлений на время"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("1 час", callback_data="disable_1h")],
            [InlineKeyboardButton("4 часа", callback_data="disable_4h")],
            [InlineKeyboardButton("24 часа", callback_data="disable_24h")],
            [InlineKeyboardButton("🔙 Назад", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔕 На какое время отключить уведомления?",
            reply_markup=reply_markup
        )
    
    async def change_workspace_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Смена пространства"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        await self.db.delete_user(user_id)
        
        keyboard = [[InlineKeyboardButton("🔗 Подключить пространство", callback_data="connect")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔄 Текущее пространство отключено.\n\n"
            "Подключите новое пространство:",
            reply_markup=reply_markup
        )
    
    async def back_to_main_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат в главное меню"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "🏠 Главное меню:",
            reply_markup=self._get_main_menu()
        )
    
    async def disable_time_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка отключения уведомлений на время"""
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        user_id = update.effective_user.id
        
        hours_map = {
            'disable_1h': 1,
            'disable_4h': 4,
            'disable_24h': 24
        }
        
        if callback_data in hours_map:
            hours = hours_map[callback_data]
            await self.settings.disable_notifications(user_id, hours)
            
            time_text = f"{hours} час{'а' if hours in [2, 3, 4] else 'ов' if hours > 4 else ''}"
            
            await query.edit_message_text(
                f"🔕 Уведомления отключены на {time_text}.\n\n"
                f"Они автоматически включатся через {time_text}.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
                ]])
            )
    
    async def enable_notifications_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Включение уведомлений"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        await self.settings.enable_notifications(user_id)
        
        await query.edit_message_text(
            "🔔 Уведомления включены!",
            reply_markup=self._get_main_menu()
        )
    
    def _get_main_menu(self):
        """Получение главного меню"""
        keyboard = [[InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]]
        return InlineKeyboardMarkup(keyboard)
    
    async def check_notifications(self):
        """Проверка новых событий и отправка уведомлений"""
        users = await self.db.get_all_users()
        
        for user in users:
            if not user['notifications_enabled']:
                continue
            
            # Проверяем временное отключение уведомлений
            if not await self.settings.are_notifications_enabled(user['user_id']):
                continue
                
            try:
                api = YonoteAPI(user['yonote_token'])
                events = await api.get_events(limit=20)
                
                if events and events.get('ok') and events.get('data'):
                    await self._process_events(user, events['data'], api)
                
                await api.close()
                
            except Exception as e:
                logger.error(f"Error checking notifications for user {user['user_id']}: {e}")
    
    async def _process_events(self, user: dict, events: list, api: YonoteAPI):
        """Обработка событий пользователя"""
        last_event_id = user.get('last_event_id')
        new_events = []
        
        for event in events:
            if last_event_id and event.get('id') == last_event_id:
                break
            new_events.append(event)
        
        if not new_events:
            return
        
        # Обновляем последний ID события
        if new_events:
            await self.db.update_last_event_id(user['user_id'], new_events[0]['id'])
        
        # Обрабатываем только события комментариев
        comment_events = [e for e in new_events if self._is_comment_event(e)]
        
        for event in comment_events:
            await self._send_notification(user['user_id'], event, api)
    
    def _is_comment_event(self, event: dict) -> bool:
        """Проверка, является ли событие связанным с комментариями"""
        event_type = event.get('name', '').lower()
        # Проверяем различные типы событий комментариев
        comment_events = [
            'comments.create',
            'comments.update', 
            'comments.delete',
            'comments.resolve',
            'comment.create',
            'comment.update',
            'comment.delete',
            'comment.resolve'
        ]
        return event_type in comment_events or any(keyword in event_type for keyword in ['comment', 'комментарий'])
    
    async def _send_notification(self, user_id: int, event: dict, api: YonoteAPI):
        """Отправка уведомления пользователю"""
        try:
            # Получаем информацию о документе
            document_id = event.get('documentId')
            if not document_id:
                return
            
            doc_info = await api.get_document_info(document_id)
            if not doc_info or not doc_info.get('ok'):
                return
            
            document = doc_info.get('data', {})
            
            # Проверяем, является ли пользователь автором или соавтором
            if not self._is_user_author_or_collaborator(event, document):
                return
            
            # Формируем уведомление
            message = self._format_notification(event, document)
            
            await self.app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")
    
    def _is_user_author_or_collaborator(self, event: dict, document: dict) -> bool:
        """Проверка, является ли пользователь автором или соавтором"""
        # Здесь нужно реализовать логику проверки авторства
        # Пока возвращаем True для всех событий
        return True
    
    def _format_notification(self, event: dict, document: dict) -> str:
        """Форматирование уведомления"""
        event_time = datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M")
        
        document_title = document.get('title', 'Без названия')
        document_url = f"https://app.yonote.ru/doc/{document.get('id', '')}"
        
        actor_name = event.get('actor', {}).get('name', 'Неизвестный пользователь')
        
        event_name = event.get('name', '')
        
        if 'create' in event_name.lower():
            action = "создал комментарий"
        elif 'update' in event_name.lower():
            action = "изменил комментарий"
        elif 'delete' in event_name.lower():
            action = "удалил комментарий"
        elif 'resolve' in event_name.lower():
            action = "изменил статус комментария"
        else:
            action = "выполнил действие с комментарием"
        
        message = f"""
📄 <b>{document_title}</b>

👤 {actor_name} {action}

🕐 {event_time} (МСК)

🔗 <a href="{document_url}">Перейти к странице</a>
"""
        
        # Добавляем текст комментария, если есть
        comment_data = event.get('data', {})
        if isinstance(comment_data, dict) and comment_data.get('data'):
            comment_text = comment_data['data'][:200]  # Ограничиваем длину
            if len(comment_data['data']) > 200:
                comment_text += "..."
            message += f"\n💬 <i>{comment_text}</i>"
        
        return message.strip()
    
    async def start_bot(self):
        """Запуск бота"""
        # Инициализация базы данных
        await self.db.init_db()
        await self.settings.init_settings_table()
        
        # Создание приложения
        self.app = Application.builder().token(BOT_TOKEN).build()
        
        # Регистрация обработчиков
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CallbackQueryHandler(self.connect_callback, pattern="connect"))
        self.app.add_handler(CallbackQueryHandler(self.settings_callback, pattern="settings"))
        self.app.add_handler(CallbackQueryHandler(self.disable_notifications_callback, pattern="disable_notifications"))
        self.app.add_handler(CallbackQueryHandler(self.change_workspace_callback, pattern="change_workspace"))
        self.app.add_handler(CallbackQueryHandler(self.back_to_main_callback, pattern="back_to_main"))
        self.app.add_handler(CallbackQueryHandler(self.disable_time_callback, pattern="^disable_[0-9]+h$"))
        self.app.add_handler(CallbackQueryHandler(self.enable_notifications_callback, pattern="enable_notifications"))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Запуск планировщика для проверки уведомлений
        self.scheduler.add_job(
            self.check_notifications,
            'interval',
            minutes=1,  # Проверяем каждую минуту
            id='check_notifications'
        )
        self.scheduler.start()
        
        # Запуск бота
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("Bot started successfully!")
        
        # Ожидание завершения
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            await self.app.stop()
            self.scheduler.shutdown()

async def main():
    """Главная функция"""
    bot = YonoteBot()
    await bot.start_bot()

if __name__ == "__main__":
    asyncio.run(main()) 