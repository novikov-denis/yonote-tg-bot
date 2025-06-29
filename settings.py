"""
Модуль для управления настройками пользователей
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import aiosqlite

class NotificationSettings:
    """Класс для управления настройками уведомлений"""
    
    def __init__(self, db_path: str = "yonote_bot.db"):
        self.db_path = db_path
        self._disabled_until: Dict[int, datetime] = {}
    
    async def init_settings_table(self):
        """Инициализация таблицы настроек"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notification_settings (
                    user_id INTEGER PRIMARY KEY,
                    disabled_until TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            await db.commit()
    
    async def disable_notifications(self, user_id: int, hours: int):
        """Отключение уведомлений на определенное время"""
        disabled_until = datetime.now() + timedelta(hours=hours)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO notification_settings (user_id, disabled_until) 
                VALUES (?, ?)
            """, (user_id, disabled_until.isoformat()))
            await db.commit()
        
        self._disabled_until[user_id] = disabled_until
    
    async def enable_notifications(self, user_id: int):
        """Включение уведомлений"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                DELETE FROM notification_settings WHERE user_id = ?
            """, (user_id,))
            await db.commit()
        
        if user_id in self._disabled_until:
            del self._disabled_until[user_id]
    
    async def are_notifications_enabled(self, user_id: int) -> bool:
        """Проверка, включены ли уведомления для пользователя"""
        # Проверяем кэш
        if user_id in self._disabled_until:
            if datetime.now() < self._disabled_until[user_id]:
                return False
            else:
                # Время истекло, удаляем из кэша и БД
                await self.enable_notifications(user_id)
                return True
        
        # Проверяем в БД
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT disabled_until FROM notification_settings WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    disabled_until = datetime.fromisoformat(row[0])
                    if datetime.now() < disabled_until:
                        self._disabled_until[user_id] = disabled_until
                        return False
                    else:
                        # Время истекло, удаляем
                        await self.enable_notifications(user_id)
                        return True
        
        return True
    
    async def get_disabled_until(self, user_id: int) -> Optional[datetime]:
        """Получение времени, до которого отключены уведомления"""
        if user_id in self._disabled_until:
            return self._disabled_until[user_id]
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT disabled_until FROM notification_settings WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return datetime.fromisoformat(row[0])
        
        return None 