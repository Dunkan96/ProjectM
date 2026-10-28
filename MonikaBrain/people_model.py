# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PersonSnapshot:
    person_id: str
    display_name: str
    role: str = "viewer"
    messages: int = 0
    affection: float = 0.0
    irritation: float = 0.0
    familiarity: float = 0.0
    aliases: list[str] = field(default_factory=list)
    bits: list[str] = field(default_factory=list)
    grievances: list[str] = field(default_factory=list)


class PeopleModel:
    """Обзор людей, которых Моника знает, без генерации ответа."""

    def __init__(self, conn, social_memory=None, creator_id: str = "Duncan"):
        self.conn = conn
        self.social_memory = social_memory
        self.creator_id = str(creator_id or "Duncan")

    def current_person(self, person_id: str, display_name: str, role: str, relationship_state: dict[str, Any] | None = None) -> PersonSnapshot:
        relationship_state = relationship_state or {}
        social = self._inspect(person_id)
        return PersonSnapshot(
            person_id=str(person_id),
            display_name=str(display_name or person_id),
            role=role,
            messages=int((relationship_state or {}).get("message_count", 0) or 0),
            affection=float((relationship_state or {}).get("affection", 0.0) or 0.0),
            irritation=float((relationship_state or {}).get("irritation", 0.0) or 0.0),
            familiarity=float((relationship_state or {}).get("familiarity", 0.0) or 0.0),
            aliases=list(social.get("aliases") or [])[:6],
            bits=list(social.get("bits") or [])[:4],
            grievances=list(social.get("grievances") or [])[:3],
        )

    def known_people(self, limit: int = 12) -> list[PersonSnapshot]:
        rows = []
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                SELECT person_id, display_name, role, affection, irritation, familiarity, message_count, last_seen
                FROM relationship_state
                ORDER BY message_count DESC, last_seen DESC
                LIMIT ?
                """,
                (int(limit),),
            )
            rows = cur.fetchall()
        except Exception:
            rows = []
        people: list[PersonSnapshot] = []
        for row in rows:
            person_id = str(row["person_id"] if hasattr(row, "keys") else row[0])
            display_name = str(row["display_name"] if hasattr(row, "keys") else row[1])
            role = str(row["role"] if hasattr(row, "keys") else row[2])
            social = self._inspect(person_id)
            people.append(PersonSnapshot(
                person_id=person_id,
                display_name=display_name or person_id,
                role=role,
                affection=float((row["affection"] if hasattr(row, "keys") else row[3]) or 0.0),
                irritation=float((row["irritation"] if hasattr(row, "keys") else row[4]) or 0.0),
                familiarity=float((row["familiarity"] if hasattr(row, "keys") else row[5]) or 0.0),
                messages=int((row["message_count"] if hasattr(row, "keys") else row[6]) or 0),
                aliases=list(social.get("aliases") or [])[:4],
                bits=list(social.get("bits") or [])[:3],
                grievances=list(social.get("grievances") or [])[:2],
            ))
        return people

    def prompt_block(self, current: PersonSnapshot, known: list[PersonSnapshot], include_known: bool) -> str:
        lines = ["[PEOPLE MODEL]", f"- Сейчас говорит: {current.display_name} ({current.role})."]
        lines.append(
            f"- Отношение: affection={current.affection:.2f}, irritation={current.irritation:.2f}, familiarity={current.familiarity:.2f}."
        )
        if current.aliases:
            lines.append("- Его/её прозвища и обращения: " + ", ".join(current.aliases[:4]) + ".")
        if current.bits:
            lines.append("- Социальные биты с ним/ней: " + " | ".join(current.bits[:3]) + ".")
        if include_known:
            if known:
                rendered = []
                for person in known[:8]:
                    rendered.append(f"{person.display_name} ({person.role}, сообщений={person.messages})")
                lines.append("- Известные люди в базе: " + "; ".join(rendered) + ".")
                lines.append("- Если спрашивают про других людей, опирайся на этот список и не выдумывай отсутствующих.")
            else:
                lines.append("- Сейчас в базе нет уверенного списка других людей.")
        return "\n".join(lines)

    def _inspect(self, person_id: str) -> dict[str, Any]:
        if not self.social_memory:
            return {}
        try:
            return self.social_memory.inspect_person(person_id)
        except Exception:
            return {}

