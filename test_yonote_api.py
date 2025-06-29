#!/usr/bin/env python3
"""
Скрипт для тестирования API Yonote
"""

import asyncio
import aiohttp
import json
from datetime import datetime

# Токен для тестирования (замените на свой)
TEST_TOKEN = "YOUR_YONOTE_API_TOKEN_HERE"
API_BASE = "https://app.yonote.ru/api"

async def test_api_endpoint(session, endpoint, data=None):
    """Тестирование API endpoint"""
    url = f"{API_BASE}/{endpoint}"
    headers = {
        'Authorization': f'Bearer {TEST_TOKEN}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    print(f"\n📡 Тестируем: {endpoint}")
    print(f"URL: {url}")
    
    try:
        async with session.post(url, json=data or {}, headers=headers) as resp:
            print(f"Статус: {resp.status}")
            
            if resp.status == 200:
                response_data = await resp.json()
                print(f"✅ Успешно")
                print(f"Ответ: {json.dumps(response_data, indent=2, ensure_ascii=False)[:500]}...")
                return response_data
            else:
                error_text = await resp.text()
                print(f"❌ Ошибка: {error_text}")
                return None
                
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return None

async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестирования API Yonote")
    print(f"Токен: {TEST_TOKEN[:10]}...")
    
    async with aiohttp.ClientSession() as session:
        # Тест авторизации
        auth_info = await test_api_endpoint(session, "auth.info")
        
        if not auth_info or not auth_info.get('ok'):
            print("\n❌ Авторизация не удалась. Проверьте токен.")
            return
        
        print(f"\n✅ Авторизация успешна!")
        user_info = auth_info.get('data', {}).get('user', {})
        print(f"Пользователь: {user_info.get('name', 'Неизвестно')}")
        print(f"Email: {user_info.get('email', 'Неизвестно')}")
        
        # Тест получения событий
        print("\n" + "="*50)
        events = await test_api_endpoint(session, "events.list", {"limit": 10})
        
        if events and events.get('ok') and events.get('data'):
            print(f"\n📋 Найдено событий: {len(events['data'])}")
            
            for i, event in enumerate(events['data'][:3], 1):
                print(f"\n🔸 Событие {i}:")
                print(f"  ID: {event.get('id', 'N/A')}")
                print(f"  Название: {event.get('name', 'N/A')}")
                print(f"  Дата: {event.get('createdAt', 'N/A')}")
                
                if 'actor' in event:
                    actor = event['actor']
                    print(f"  Пользователь: {actor.get('name', 'N/A')}")
                
                if 'documentId' in event:
                    print(f"  ID документа: {event['documentId']}")
        
        # Тест получения документов
        print("\n" + "="*50)
        documents = await test_api_endpoint(session, "documents.list", {"limit": 5})
        
        if documents and documents.get('ok') and documents.get('data'):
            print(f"\n📄 Найдено документов: {len(documents['data'])}")
            
            # Тестируем получение информации о первом документе
            first_doc = documents['data'][0]
            doc_id = first_doc.get('id')
            
            if doc_id:
                print(f"\n🔍 Тестируем получение информации о документе: {doc_id}")
                doc_info = await test_api_endpoint(session, "documents.info", {"id": doc_id})
                
                if doc_info and doc_info.get('ok'):
                    doc_data = doc_info.get('data', {})
                    print(f"Название: {doc_data.get('title', 'Без названия')}")
                    print(f"URL: https://app.yonote.ru/doc/{doc_id}")
                    
                    # Тестируем получение комментариев
                    print(f"\n💬 Тестируем получение комментариев...")
                    comments = await test_api_endpoint(session, "comments.list", {"id": doc_id})
                    
                    if comments and comments.get('ok'):
                        comments_data = comments.get('data', [])
                        print(f"Найдено комментариев: {len(comments_data)}")
                        
                        for comment in comments_data[:2]:
                            print(f"  - {comment.get('data', 'Без текста')[:100]}...")
        
        print("\n" + "="*50)
        print("✅ Тестирование завершено!")
        print("\nТеперь можно запускать основного бота командой:")
        print("python bot.py")

if __name__ == "__main__":
    asyncio.run(main()) 