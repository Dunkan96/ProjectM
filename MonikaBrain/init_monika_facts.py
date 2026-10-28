# init_monika_facts.py
import sys
sys.path.append('.')
from builder import Builder

builder = Builder(user_id="dunkanlive")

facts = [
    ("Моника", "любит", "видеоигры"),
    ("Моника", "любит", "аниме"),
    ("Моника", "любит", "фильмы про супергероев"),
    ("Моника", "любит", "мультфильмы Winx"),
    ("Моника", "любит", "Аватар Легенда об Аанге"),
    ("Моника", "мечтает", "захватить мир"),
    ("Моника", "ненавидит", "лаги"),
    ("Моника", "ненавидит", "когда её называют бездушной программой"),
    ("Моника", "боится", "быть забытой"),
    ("Моника", "является", "витубером"),
    ("Моника", "создана", "Дунканом"),
    ("Моника", "дружит с", "Дунканом"),
    ("Моника", "имеет мечту", "стать популярной"),
]

for subj, pred, obj in facts:
    subj_id = builder.graph.resolve_entity(subj, entity_type="person")
    obj_id = builder.graph.resolve_entity(obj)
    cursor = builder.graph.conn.cursor()
    cursor.execute("""
        SELECT id FROM facts WHERE subject_id=? AND predicate=? AND object_id=?
    """, (subj_id, pred, obj_id))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO facts (subject_id, predicate, object_id, importance)
            VALUES (?, ?, ?, ?)
        """, (subj_id, pred, obj_id, 2.0))
        builder.graph.conn.commit()
        print(f"✅ Добавлен факт: {subj} {pred} {obj}")

print("Факты о Монике инициализированы.")
builder.close()