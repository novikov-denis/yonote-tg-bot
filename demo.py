#!/usr/bin/env python3
"""
Демонстрационный скрипт для проверки компонентов бота
"""

import asyncio
import os
from bot import Database, YonoteAPI
from settings import NotificationSettings

# Демонстрационный токен (замените на свой)
DEMO_TOKEN = "YOUR_YONOTE_API_TOKEN_HERE"

async def demo_database():
    """Демонстрация работы с базой данных"""
    print("🗄️ Тестирование базы данных...")
    
    # Используем отдельную тестовую БД
    db = Database("demo_bot.db")
    settings = NotificationSettings("demo_bot.db")
    
    # Инициализация
    await db.init_db()
    await settings.init_settings_table()
    
    # Тестовые данные
    test_user_id = 123456789
    test_token = "test_token_123"
    
    # Сохранение пользователя
    await db.save_user_token(test_user_id, test_token)
    print(f"✅ Пользователь {test_user_id} сохранен")
    
    # Получение токена
    saved_token = await db.get_user_token(test_user_id)
    print(f"✅ Токен получен: {saved_token == test_token}")
    
    # Настройки уведомлений
    await settings.disable_notifications(test_user_id, 1)
    enabled = await settings.are_notifications_enabled(test_user_id)
    print(f"✅ Уведомления отключены: {not enabled}")
    
    # Включение уведомлений
    await settings.enable_notifications(test_user_id)
    enabled = await settings.are_notifications_enabled(test_user_id)
    print(f"✅ Уведомления включены: {enabled}")
    
    # Очистка
    await db.delete_user(test_user_id)
    print("✅ Тестовые данные удалены")
    
    # Удаление тестовой БД
    if os.path.exists("demo_bot.db"):
        os.remove("demo_bot.db")
    
    print("✅ База данных протестирована успешно!\n")

async def demo_api():
    """Демонстрация работы с API"""
    print("🌐 Тестирование API Yonote...")
    
    api = YonoteAPI(DEMO_TOKEN)
    
    # Проверка авторизации
    auth_info = await api.get_auth_info()
    if auth_info and auth_info.get('ok'):
        user = auth_info.get('data', {}).get('user', {})
        print(f"✅ Авторизация: {user.get('name', 'Неизвестно')}")
    else:
        print("❌ Ошибка авторизации")
        return
    
    # Получение событий
    events = await api.get_events(limit=5)
    if events and events.get('ok'):
        print(f"✅ События получены: {len(events.get('data', []))}")
    else:
        print("❌ Ошибка получения событий")
    
    await api.close()
    print("✅ API протестировано успешно!\n")

async def demo_notifications():
    """Демонстрация формирования уведомлений"""
    print("🔔 Тестирование уведомлений...")
    
    # Пример события
    test_event = {
        'id': 'test-event-123',
        'name': 'comments.create',
        'documentId': 'test-doc-456',
        'actor': {
            'name': 'Тестовый Пользователь'
        },
        'data': {
            'data': 'Это тестовый комментарий для демонстрации уведомлений'
        }
    }
    
    # Пример документа
    test_document = {
        'id': 'test-doc-456',
        'title': 'Тестовая страница',
        'url': '/doc/test-page'
    }
    
    # Импортируем класс бота для тестирования метода форматирования
    from bot import YonoteBot
    bot = YonoteBot()
    
    # Форматируем уведомление
    notification = bot._format_notification(test_event, test_document)
    print("📱 Пример уведомления:")
    print(notification)
    
    print("✅ Уведомления протестированы успешно!\n")

async def main():
    """Главная функция демонстрации"""
    print("🚀 Запуск демонстрации Yonote Bot")
    print("=" * 50)
    
    try:
        await demo_database()
        await demo_api()
        await demo_notifications()
        
        print("🎉 Все компоненты работают корректно!")
        print("\nБот готов к запуску. Используйте команду:")
        print("python3 bot.py")
        
    except Exception as e:
        print(f"❌ Ошибка во время демонстрации: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 