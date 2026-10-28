import sqlite3
from typing import Any, Dict, Optional


class SocialLayer:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_table()
        self._ensure_columns()

    def _init_table(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS relationship_state (
                person_id TEXT PRIMARY KEY,
                display_name TEXT,
                role TEXT DEFAULT 'guest',
                affection REAL DEFAULT 0.0,
                trust REAL DEFAULT 0.0,
                irritation REAL DEFAULT 0.0,
                interest REAL DEFAULT 0.0,
                respect REAL DEFAULT 0.0,
                familiarity REAL DEFAULT 0.0,
                boundary_risk REAL DEFAULT 0.0,
                alliance REAL DEFAULT 0.0,
                friction REAL DEFAULT 0.0,
                inside_jokes INTEGER DEFAULT 0,
                impression TEXT DEFAULT '',
                message_count INTEGER DEFAULT 0,
                positive_count INTEGER DEFAULT 0,
                negative_count INTEGER DEFAULT 0,
                last_event TEXT DEFAULT 'neutral',
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def _ensure_columns(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(relationship_state)")
        existing = {row[1] for row in cursor.fetchall()}
        additions = {
            "alliance": "REAL DEFAULT 0.0",
            "friction": "REAL DEFAULT 0.0",
            "inside_jokes": "INTEGER DEFAULT 0",
            "impression": "TEXT DEFAULT ''",
            "moderation_count": "INTEGER DEFAULT 0",
            "last_moderation_action": "TEXT DEFAULT 'none'",
        }
        for column, definition in additions.items():
            if column not in existing:
                cursor.execute(f"ALTER TABLE relationship_state ADD COLUMN {column} {definition}")
        self.conn.commit()

    def ensure_person(self, person_id: str, display_name: str | None = None, role: str = "guest") -> None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT person_id FROM relationship_state WHERE person_id = ?", (person_id,))
        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE relationship_state
                SET display_name = COALESCE(?, display_name),
                    role = COALESCE(?, role),
                    last_seen = CURRENT_TIMESTAMP
                WHERE person_id = ?
                """,
                (display_name, role, person_id),
            )
        else:
            base_affection = 0.6 if role == "creator" else 0.1
            base_trust = 0.8 if role == "creator" else 0.05
            base_respect = 0.9 if role == "creator" else 0.1
            base_alliance = 0.7 if role == "creator" else 0.1
            cursor.execute(
                """
                INSERT INTO relationship_state (
                    person_id, display_name, role, affection, trust, respect,
                    familiarity, alliance, impression
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    person_id,
                    display_name,
                    role,
                    base_affection,
                    base_trust,
                    base_respect,
                    0.05,
                    base_alliance,
                    self._impression_for_role(role),
                ),
            )
        self.conn.commit()

    def update_interaction(
        self,
        person_id: str,
        display_name: str | None,
        role: str,
        text: str,
        sentiment: float,
        event_type: str = "neutral",
        violation_type: str | None = None,
    ) -> Dict[str, Any]:
        self.ensure_person(person_id, display_name, role)
        state = self.get_state(person_id) or {}

        affection = float(state.get("affection", 0.0) or 0.0)
        trust = float(state.get("trust", 0.0) or 0.0)
        irritation = float(state.get("irritation", 0.0) or 0.0)
        interest = float(state.get("interest", 0.0) or 0.0)
        respect = float(state.get("respect", 0.0) or 0.0)
        familiarity = float(state.get("familiarity", 0.0) or 0.0)
        boundary_risk = float(state.get("boundary_risk", 0.0) or 0.0)
        alliance = float(state.get("alliance", 0.0) or 0.0)
        friction = float(state.get("friction", 0.0) or 0.0)
        inside_jokes = int(state.get("inside_jokes", 0) or 0)
        message_count = int(state.get("message_count", 0) or 0) + 1
        positive_count = int(state.get("positive_count", 0) or 0)
        negative_count = int(state.get("negative_count", 0) or 0)

        text_lower = (text or "").lower()
        affection += sentiment * 0.18
        trust += sentiment * 0.12
        interest += 0.03
        familiarity += 0.03
        respect += 0.02 if role == "creator" else sentiment * 0.05
        alliance += sentiment * 0.14
        friction += max(0.0, -sentiment) * 0.1

        if event_type == "praise":
            affection += 0.08
            trust += 0.05
            alliance += 0.06
            positive_count += 1
        elif event_type == "personal":
            affection += 0.04
            interest += 0.05
            alliance += 0.03
        elif event_type == "insult":
            irritation += 0.12
            affection -= 0.08
            trust -= 0.05
            boundary_risk += 0.12
            friction += 0.14
            negative_count += 1

        if violation_type == "hate":
            irritation += 0.18
            trust -= 0.08
            affection -= 0.14
            boundary_risk += 0.24
            friction += 0.22
            negative_count += 1
        elif violation_type == "forbidden":
            boundary_risk += 0.08
            irritation += 0.03
            friction += 0.05

        if any(token in text_lower for token in ["спасибо", "люблю", "крутая", "молодец", "умница"]):
            affection += 0.05
            trust += 0.03
            alliance += 0.04
            positive_count += 1

        if any(token in text_lower for token in ["тупая", "дура", "бот", "бездарь", "заткнись"]):
            irritation += 0.12
            affection -= 0.08
            boundary_risk += 0.12
            friction += 0.14
            negative_count += 1

        if any(token in text_lower for token in ["давай поговорим", "как дела", "привет", "ты тут", "расскажи"]):
            interest += 0.03
        if any(token in text_lower for token in ["ахах", "лол", "ору", "пхах", "угар", "кринж"]):
            inside_jokes += 1
            alliance += 0.03
        if any(token in text_lower for token in ["вместе", "с тобой", "мы ", "наш "]):
            alliance += 0.04

        # Усиленный decay раздражения
        irritation_decay = 0.14 if irritation >= 0.65 else 0.09 if irritation >= 0.3 else 0.05
        irritation = max(0.0, irritation - irritation_decay)
        boundary_risk = max(0.0, boundary_risk - 0.08)
        friction = max(0.0, friction - 0.07)

        updated = {
            "person_id": person_id,
            "display_name": display_name or state.get("display_name") or person_id,
            "role": role,
            "affection": self._clamp(affection, -1.0, 1.0),
            "trust": self._clamp(trust, -1.0, 1.0),
            "irritation": self._clamp(irritation, 0.0, 1.0),
            "interest": self._clamp(interest, 0.0, 1.0),
            "respect": self._clamp(respect, -1.0, 1.0),
            "familiarity": self._clamp(familiarity, 0.0, 1.0),
            "boundary_risk": self._clamp(boundary_risk, 0.0, 1.5),
            "alliance": self._clamp(alliance, -1.0, 1.0),
            "friction": self._clamp(friction, 0.0, 1.0),
            "inside_jokes": max(0, inside_jokes),
            "impression": self._compute_impression(
                role=role,
                affection=affection,
                trust=trust,
                irritation=irritation,
                alliance=alliance,
                friction=friction,
                familiarity=familiarity,
            ),
            "message_count": message_count,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "last_event": violation_type or event_type or "neutral",
            "moderation_count": int(state.get("moderation_count", 0) or 0),
            "last_moderation_action": state.get("last_moderation_action", "none"),
        }
        self._save_state(updated)
        return updated

    def get_state(self, person_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM relationship_state WHERE person_id = ?", (person_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def build_prompt_block(self, person_id: str, role: str) -> str:
        state = self.get_state(person_id)
        if not state:
            return ""
        lines = [
            "[ОТНОШЕНИЕ К СОБЕСЕДНИКУ]",
            f"- Это {self._role_note(role)}.",
            f"- Текущая близость: {state['affection']:.2f}; доверие: {state['trust']:.2f}; раздражение: {state['irritation']:.2f}; интерес: {state['interest']:.2f}.",
            f"- Манера общения сейчас: {self._style_note(state)}.",
            f"- Общее впечатление о человеке: {state.get('impression') or self._impression_for_role(role)}.",
        ]
        if int(state.get("inside_jokes", 0) or 0) > 0:
            lines.append(f"- У вас уже есть локальные общие приколы: {int(state.get('inside_jokes', 0) or 0)}.")
        risk = float(state.get("boundary_risk", 0.0) or 0.0)
        moderation_count = int(state.get("moderation_count", 0) or 0)
        last_action = (state.get("last_moderation_action") or "none").strip()
        if moderation_count > 0 and last_action != "none":
            lines.append(f"- РџРѕ РіСЂР°РЅРёС†Р°Рј СѓР¶Рµ Р±С‹Р»Рё РјРµСЂС‹: {moderation_count} СЂР°Р·(Р°), РїРѕСЃР»РµРґРЅРµРµ РґРµР№СЃС‚РІРёРµ: {last_action}.")
        if risk >= 1.15:
            lines.append("- Этот человек уже близок к границе терпения. Не заискивай и не поощряй плохое поведение.")
        elif risk >= 0.8:
            lines.append("- С ним уже есть напряжение, так что держи границы и не становись слишком мягкой.")
        return "\n".join(lines)

    def get_relationship_hint(self, person_id: str, role: str) -> str:
        state = self.get_state(person_id)
        if not state:
            return ""
        return self._style_note(state)

    def moderation_action(self, person_id: str) -> str:
        state = self.get_state(person_id)
        if not state:
            return "none"
        if (state.get("role") or "").strip() == "creator":
            return "none"
        boundary_risk = float(state.get("boundary_risk", 0.0) or 0.0)
        irritation = float(state.get("irritation", 0.0) or 0.0)
        moderation_count = int(state.get("moderation_count", 0) or 0)
        last_action = (state.get("last_moderation_action") or "none").strip()
        last_event = (state.get("last_event") or "neutral").strip()
        if boundary_risk >= 1.4 or moderation_count >= 6:
            return "ban"
        if (
            boundary_risk >= 1.05
            or irritation >= 0.96
            or last_action == "warn"
            or (last_event == "hate" and (boundary_risk >= 0.8 or irritation >= 0.8))
        ):
            return "timeout"
        if (
            boundary_risk >= 0.8
            or moderation_count >= 3
            or (last_event in {"hate", "forbidden"} and (boundary_risk >= 0.5 or irritation >= 0.5))
        ):
            return "warn"
        return "none"

    def register_moderation(self, person_id: str, action: str) -> Dict[str, Any]:
        state = self.get_state(person_id)
        if not state or action in {"", "none"}:
            return state or {}
        if (state.get("role") or "").strip() == "creator":
            return state
        updated = dict(state)
        updated["moderation_count"] = int(updated.get("moderation_count", 0) or 0) + 1
        updated["last_moderation_action"] = action
        if action == "warn":
            updated["irritation"] = self._clamp(float(updated.get("irritation", 0.0) or 0.0) + 0.01, 0.0, 1.0)
            updated["boundary_risk"] = self._clamp(float(updated.get("boundary_risk", 0.0) or 0.0) + 0.02, 0.0, 1.5)
        elif action == "timeout":
            updated["irritation"] = self._clamp(float(updated.get("irritation", 0.0) or 0.0) + 0.02, 0.0, 1.0)
            updated["boundary_risk"] = self._clamp(float(updated.get("boundary_risk", 0.0) or 0.0) + 0.04, 0.0, 1.5)
            updated["trust"] = self._clamp(float(updated.get("trust", 0.0) or 0.0) - 0.02, -1.0, 1.0)
        elif action == "ban":
            updated["irritation"] = self._clamp(float(updated.get("irritation", 0.0) or 0.0) + 0.04, 0.0, 1.0)
            updated["boundary_risk"] = self._clamp(float(updated.get("boundary_risk", 0.0) or 0.0) + 0.08, 0.0, 1.5)
            updated["trust"] = self._clamp(float(updated.get("trust", 0.0) or 0.0) - 0.04, -1.0, 1.0)
            updated["affection"] = self._clamp(float(updated.get("affection", 0.0) or 0.0) - 0.04, -1.0, 1.0)
        self._save_state(updated)
        return self.get_state(person_id) or updated

    def _save_state(self, state: Dict[str, Any]) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE relationship_state
            SET display_name = ?,
                role = ?,
                affection = ?,
                trust = ?,
                irritation = ?,
                interest = ?,
                respect = ?,
                familiarity = ?,
                boundary_risk = ?,
                alliance = ?,
                friction = ?,
                inside_jokes = ?,
                impression = ?,
                message_count = ?,
                positive_count = ?,
                negative_count = ?,
                last_event = ?,
                moderation_count = ?,
                last_moderation_action = ?,
                last_seen = CURRENT_TIMESTAMP
            WHERE person_id = ?
            """,
            (
                state["display_name"],
                state["role"],
                state["affection"],
                state["trust"],
                state["irritation"],
                state["interest"],
                state["respect"],
                state["familiarity"],
                state["boundary_risk"],
                state["alliance"],
                state["friction"],
                state["inside_jokes"],
                state["impression"],
                state["message_count"],
                state["positive_count"],
                state["negative_count"],
                state["last_event"],
                int(state.get("moderation_count", 0) or 0),
                state.get("last_moderation_action", "none"),
                state["person_id"],
            ),
        )
        self.conn.commit()

    def _style_note(self, state: Dict[str, Any]) -> str:
        affection = float(state.get("affection", 0.0) or 0.0)
        trust = float(state.get("trust", 0.0) or 0.0)
        irritation = float(state.get("irritation", 0.0) or 0.0)
        familiarity = float(state.get("familiarity", 0.0) or 0.0)
        alliance = float(state.get("alliance", 0.0) or 0.0)
        if irritation >= 0.9:
            return "можно отвечать суше и жёстче, границы важнее тепла"
        if affection >= 0.55 and trust >= 0.45:
            return "можно звучать ближе, живее и чуть более лично"
        if alliance >= 0.45:
            return "с ним уже чувствуется своя химия, можно позволять больше живости и локальных подколов"
        if familiarity >= 0.45:
            return "человек уже свой, можно вести себя свободнее и теплее"
        return "держи лёгкий естественный тон без лишней дистанции"

    def _role_note(self, role: str) -> str:
        notes = {
            "creator": "создатель, у тебя к нему особая близость и высокий кредит доверия",
            "viewer": "зритель, важен сценический, но не безличный тон",
            "guest": "новый или случайный человек, дружелюбие без лишней фамильярности",
            "scene": "сама сцена, тут нужна реакция на момент, а не социальная близость",
        }
        return notes.get(role, notes["guest"])

    def _impression_for_role(self, role: str) -> str:
        mapping = {
            "creator": "свой человек, к которому тянет ближе и свободнее",
            "viewer": "зритель, которого хочется вовлекать и читать по реакции",
            "guest": "ещё не свой, но потенциально интересный человек",
            "scene": "не человек, а сам момент сцены, на который надо реагировать",
        }
        return mapping.get(role, mapping["guest"])

    def _compute_impression(
        self,
        role: str,
        affection: float,
        trust: float,
        irritation: float,
        alliance: float,
        friction: float,
        familiarity: float,
    ) -> str:
        if irritation >= 0.9 or friction >= 0.9:
            return "раздражает и требует жёстче держать границы"
        if role == "creator" and trust >= 0.65:
            return "мой человек, с которым можно быть смелее, живее и местами наглее"
        if alliance >= 0.55 and familiarity >= 0.45:
            return "свой по вайбу, можно держать локальные приколы и не звучать формально"
        if affection >= 0.45:
            return "приятный человек, к которому тянет теплее и мягче"
        if familiarity >= 0.35:
            return "уже не чужой, можно меньше держать дистанцию"
        return self._impression_for_role(role)
    def forgive(self, person_id: str) -> Dict[str, Any]:
        """Сбросить раздражение и риск для пользователя."""
        state = self.get_state(person_id)
        if not state:
            return {}
        updated = dict(state)
        updated["irritation"] = 0.0
        updated["boundary_risk"] = 0.0
        updated["friction"] = 0.0
        updated["moderation_count"] = 0
        updated["last_moderation_action"] = "none"
        updated["impression"] = self._impression_for_role(state.get("role", "guest"))
        updated["affection"] = max(float(updated.get("affection", 0.0) or 0.0), 0.3)
        updated["trust"] = max(float(updated.get("trust", 0.0) or 0.0), 0.3)
        self._save_state(updated)
        return self.get_state(person_id) or updated
        
    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
