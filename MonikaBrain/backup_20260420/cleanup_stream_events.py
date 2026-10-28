import sqlite3
import os
from config import BRAIN_DIR

db_path = os.path.join(BRAIN_DIR, 'knowledge.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("DELETE FROM stream_events WHERE event_type = 'session_summary'")
conn.commit()
conn.close()

print("Старые сводки удалены. Запускай !консолидация.")