# reset_brain.py
"""
Скрипт полной очистки мозга Моники.
Удаляет все данные: кэш, историю чата, факты, сущности, эмоциональную память.
Запускать перед тестированием с чистого листа.
"""

import os
import shutil
import sqlite3
import sys

def confirm(message):
    """Запрашивает подтверждение у пользователя."""
    response = input(f"{message} (y/N): ").strip().lower()
    return response in ['y', 'yes', 'да', 'д']

def reset_brain():
    print("=" * 60)
    print("🧹 СБРОС МОЗГА МОНИКИ ДО ЗАВОДСКИХ НАСТРОЕК")
    print("=" * 60)
    print()
    print("ВНИМАНИЕ! Это удалит ВСЕ данные Моники:")
    print("  - Кэш ответов (ChromaDB)")
    print("  - Историю чата")
    print("  - Факты и сущности графа знаний")
    print("  - Эмоциональную память")
    print("  - Engram память (нужно очистить отдельно через дашборд)")
    print()
    
    if not confirm("Продолжить?"):
        print("❌ Отмена.")
        return
    
    cleaned = []
    failed = []
    
    # 1. Очистка кэша ChromaDB
    print("\n[1/4] Очистка кэша ChromaDB...")
    chroma_path = "./chroma_engram"
    if os.path.exists(chroma_path):
        try:
            shutil.rmtree(chroma_path)
            print(f"  ✅ {chroma_path} удалён")
            cleaned.append("ChromaDB кэш")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            failed.append("ChromaDB кэш")
    else:
        print(f"  ⏭️ {chroma_path} не найден")
    
    # 2. Очистка истории чата в knowledge.db
    print("\n[2/4] Очистка истории чата...")
    knowledge_db = "knowledge.db"
    if os.path.exists(knowledge_db):
        try:
            conn = sqlite3.connect(knowledge_db)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_history")
            conn.commit()
            conn.close()
            print(f"  ✅ История чата очищена")
            cleaned.append("История чата")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            failed.append("История чата")
    else:
        print(f"  ⏭️ {knowledge_db} не найден")
    
    # 3. Очистка фактов и сущностей в monika_memory.db
    print("\n[3/4] Очистка графа знаний...")
    memory_db = "monika_memory.db"
    if os.path.exists(memory_db):
        try:
            conn = sqlite3.connect(memory_db)
            cursor = conn.cursor()
            
            # Сначала удаляем факты
            cursor.execute("DELETE FROM facts")
            facts_deleted = cursor.rowcount
            
            # Потом сущности
            cursor.execute("DELETE FROM entities")
            entities_deleted = cursor.rowcount
            
            conn.commit()
            conn.close()
            print(f"  ✅ Удалено фактов: {facts_deleted}, сущностей: {entities_deleted}")
            cleaned.append("Граф знаний")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            failed.append("Граф знаний")
    else:
        print(f"  ⏭️ {memory_db} не найден")
    
    # 4. Очистка эмоциональной памяти в knowledge.db
    print("\n[4/4] Очистка эмоциональной памяти...")
    if os.path.exists(knowledge_db):
        try:
            conn = sqlite3.connect(knowledge_db)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM emotional_memory")
            conn.commit()
            conn.close()
            print(f"  ✅ Эмоциональная память очищена")
            cleaned.append("Эмоциональная память")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            failed.append("Эмоциональная память")
    
    # Удаление файлов статистики и логов
    print("\n[Дополнительно] Очистка логов...")
    for file in ["timing_stats.json", "timing_stats_final.json", "crash_log.txt"]:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"  ✅ {file} удалён")
            except Exception as e:
                print(f"  ❌ Ошибка удаления {file}: {e}")
    
    # Очистка last_cleanup.txt
    cleanup_file = "last_cleanup.txt"
    if os.path.exists(cleanup_file):
        try:
            os.remove(cleanup_file)
            print(f"  ✅ {cleanup_file} удалён")
        except Exception as e:
            print(f"  ❌ Ошибка удаления {cleanup_file}: {e}")
    
    # Итог
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ОЧИСТКИ")
    print("=" * 60)
    if cleaned:
        print(f"✅ Успешно очищено ({len(cleaned)}):")
        for item in cleaned:
            print(f"   - {item}")
    if failed:
        print(f"❌ Ошибки ({len(failed)}):")
        for item in failed:
            print(f"   - {item}")
    
    print()
    print("💡 ПРИМЕЧАНИЕ:")
    print("   Engram память нужно очистить вручную через дашборд:")
    print("   http://localhost:3838 → Memories → Выбрать все → Delete")
    print()
    print("🎉 Готово! Можно запускать Монику с чистым мозгом.")

if __name__ == "__main__":
    reset_brain()