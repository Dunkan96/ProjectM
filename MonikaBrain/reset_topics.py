# reset_topics.py
import sqlite3

conn = sqlite3.connect('knowledge.db')
cursor = conn.cursor()

# Очищаем таблицу topic_weights
cursor.execute("DELETE FROM topic_weights")
conn.commit()

# Проверяем, сколько записей осталось
cursor.execute("SELECT COUNT(*) FROM topic_weights")
count = cursor.fetchone()[0]
print(f"✅ Таблица topic_weights очищена. Осталось записей: {count}")

conn.close()