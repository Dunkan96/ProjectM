# -*- coding: utf-8 -*-
from __future__ import annotations

import difflib
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "autonomous_memory_v1h"

OLD_NICKNAME_BLACKLIST = {
    "дунканоид", "главный балда", "тестировщик моей психики", "балда с твич",
    "балда с душой", "мастер стримов", "стрим магнат", "босс со стрима",
    "повелитель костылей", "дунканыч", "дункан",
}

BAD_NICKNAME_FRAGMENTS = (
    "выполняй задач", "и себя", "хочу спать", "всегда прав", "интеллектуаль",
    "что ты", "что из", "как ты", "факт", "память", "воспомин", "кринж",
    "удал", "забы", "стереть", "не называй", "называй меня", "ахаха", "норм", "привет",
)

FRESH_NICKNAME_POOL = [
    "Лорд Горячих Клавиш", "Капитан Перезапуск", "Баговый шаман", "Командир Краш-тестов",
    "Граф Синих Проводов", "Архимаг Бэкапов", "Патчевый рыцарь", "Маэстро Рестартов",
    "Клавиатурный колдун", "Хранитель Логов", "Барон Фреймдропа", "Повелитель Конфига",
    "Рыцарь Синего Экрана", "Шёпот Компилятора", "Герцог Горячих Фиксов",
]

ACCEPT_WORDS = ("норм", "нормально", "круто", "годно", "принима", "остав", "понрав", "ахаха", "хаха", "зачет", "зачёт", "подходит", "ок", "окей")
REJECT_WORDS = ("не называй", "не зови", "не используй", "не хочу чтобы ты называла", "не хочу чтобы называла", "не надо меня так", "хватит так", "убери кличку")
MEMORY_PHILOSOPHY_HINTS = ("удалить воспомин", "удали воспомин", "стереть воспомин", "забыть воспомин", "можешь забыть", "можешь удалить", "кринжовый момент", "кринж", "стыдно", "как ты будешь вспоминать", "что важно помнить", "что стоит помнить", "память", "воспоминание")


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def normalize_key(text: str) -> str:
    text = str(text or "").lower().replace("ё", "е")
    text = re.sub(r"[\"'`«»“”„]", " ", text)
    text = re.sub(r"[^0-9a-zа-я_\- ]+", " ", text, flags=re.I)
    text = text.replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    a, b = normalize_key(a), normalize_key(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        shorter, longer = min(len(a), len(b)), max(len(a), len(b))
        if shorter >= 5:
            return max(0.86, shorter / max(1, longer))
    return difflib.SequenceMatcher(None, a, b).ratio()


def split_objects(raw: str) -> List[str]:
    raw = re.sub(r"\([^)]*\)", " ", raw or "")
    raw = re.sub(r"[.!?;:]+", ",", raw)
    raw = re.sub(r"\s+(?:и|да еще|да ещё|ещё|еще)\s+", ",", raw, flags=re.I)
    out: List[str] = []
    for p in raw.split(","):
        p = p.strip(" ,.-—–\t\r\n")
        p = re.sub(r"^(?:а|но|вот|это|просто|мой|моя|мое|моё)\s+", "", p, flags=re.I).strip()
        p = re.sub(r"\s+", " ", p)
        if 2 <= len(p) <= 50 and not re.search(r"\b(я|ты|она|он|мы|вы|они|мне|меня|тебя)\b$", normalize_key(p)):
            out.append(p)
    return out[:6]


class AutonomousMemoryGovernor:
    def __init__(self, db_or_conn: Any = None):
        self._own_conn = False
        if isinstance(db_or_conn, sqlite3.Connection):
            self.conn = db_or_conn
        else:
            self.conn = sqlite3.connect(str(db_or_conn or "knowledge.db"))
            self._own_conn = True
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        if self._own_conn:
            self.conn.close()

    def init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS autonomous_memory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL, kind TEXT NOT NULL,
            subject TEXT NOT NULL, predicate TEXT DEFAULT '', value TEXT DEFAULT '', stance TEXT DEFAULT '',
            status TEXT DEFAULT 'candidate', confidence REAL DEFAULT 0.65, source_text TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS social_nicknames (
            id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL, nickname TEXT NOT NULL,
            normalized TEXT NOT NULL, status TEXT DEFAULT 'proposed', tone TEXT DEFAULT 'teasing',
            source_event TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_used_at TEXT DEFAULT CURRENT_TIMESTAMP, use_count INTEGER DEFAULT 0,
            positive_reactions INTEGER DEFAULT 0, negative_reactions INTEGER DEFAULT 0,
            UNIQUE(person_id, normalized))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS memory_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL, correction_type TEXT NOT NULL,
            text TEXT NOT NULL, status TEXT DEFAULT 'candidate', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS monika_experience_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL, event_type TEXT NOT NULL,
            status TEXT DEFAULT 'active', stage TEXT DEFAULT '', cringe_score REAL DEFAULT 0.0,
            summary TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS memory_action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action_type TEXT NOT NULL, person_id TEXT DEFAULT '',
            target TEXT DEFAULT '', status TEXT DEFAULT 'ok', detail TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        self._ensure_columns()
        self.conn.commit()

    def _ensure_columns(self) -> None:
        expected = {
            "autonomous_memory_items": {"predicate":"TEXT DEFAULT ''", "value":"TEXT DEFAULT ''", "stance":"TEXT DEFAULT ''", "status":"TEXT DEFAULT 'candidate'", "confidence":"REAL DEFAULT 0.65", "source_text":"TEXT DEFAULT ''", "updated_at":"TEXT DEFAULT CURRENT_TIMESTAMP"},
            "social_nicknames": {"tone":"TEXT DEFAULT 'teasing'", "source_event":"TEXT DEFAULT ''", "last_used_at":"TEXT DEFAULT CURRENT_TIMESTAMP", "use_count":"INTEGER DEFAULT 0", "positive_reactions":"INTEGER DEFAULT 0", "negative_reactions":"INTEGER DEFAULT 0"},
            "monika_experience_journal": {"stage":"TEXT DEFAULT ''", "cringe_score":"REAL DEFAULT 0.0"},
        }
        cur = self.conn.cursor()
        for table, cols in expected.items():
            cur.execute(f"PRAGMA table_info({table})")
            have = {r[1] for r in cur.fetchall()}
            for col, decl in cols.items():
                if col not in have:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    def _coerce_turn_args(self, *args: Any, **kwargs: Any):
        person_id = kwargs.get("person_id") or kwargs.get("social_person_id") or kwargs.get("viewer_id") or "Duncan"
        user_text = kwargs.get("user_text") or kwargs.get("user_input") or kwargs.get("input_text") or kwargs.get("message") or ""
        monika_reply = kwargs.get("monika_reply") or kwargs.get("reply") or kwargs.get("assistant_reply") or kwargs.get("output_text") or ""
        stage = kwargs.get("stage") or kwargs.get("scene_stage") or kwargs.get("mode") or ""
        if args:
            if len(args) >= 3:
                if isinstance(args[0], str) and args[0] and len(args[0]) < 80 and not re.search(r"\s", args[0].strip()):
                    person_id, user_text, monika_reply = args[0], str(args[1]), str(args[2])
                    if len(args) >= 4: stage = str(args[3] or "")
                else:
                    user_text, monika_reply = str(args[0]), str(args[1])
                    stage = str(args[2] or "")
            elif len(args) == 2:
                user_text, monika_reply = str(args[0]), str(args[1])
            elif len(args) == 1:
                user_text = str(args[0])
        return str(person_id or "Duncan"), str(user_text or ""), str(monika_reply or ""), str(stage or "")

    def build_prompt_block(self, *args: Any, **kwargs: Any) -> str:
        person_id, user_text, _, stage = self._coerce_turn_args(*args, **kwargs)
        return self._build_prompt_block(person_id, user_text, stage)

    def observe_turn(self, *args: Any, **kwargs: Any) -> None:
        person_id, user_text, monika_reply, stage = self._coerce_turn_args(*args, **kwargs)
        try:
            self._observe_turn(person_id, user_text, monika_reply, stage)
        except Exception as e:
            self._log("autonomous_error", person_id, "", "error", f"observe_turn: {e}")

    def repair_reply(self, *args: Any, **kwargs: Any) -> str:
        person_id, user_text, monika_reply, stage = self._coerce_turn_args(*args, **kwargs)
        try:
            return self._repair_reply(person_id, user_text, monika_reply, stage)
        except Exception as e:
            self._log("autonomous_error", person_id, "", "error", f"repair_reply: {e}")
            return monika_reply

    def normalize_for_intent(self, text: str) -> str:
        t = normalize_key(text)
        address = r"(привет|ты|слушай|скажи|помнишь|думаешь|что|как|эй|алло|тут)"
        t = re.sub(r"^(моник|моня|мони|моничка)\b", "моника", t)
        if re.match(rf"^монитор\s+{address}\b", t):
            t = re.sub(r"^монитор\b", "моника", t)
        return t

    def _observe_turn(self, person_id: str, user_text: str, monika_reply: str, stage: str = "") -> None:
        self.init_schema()
        semantic_user = self.normalize_for_intent(user_text)
        self._observe_nickname_reaction(person_id, semantic_user)
        self._observe_user_preferences(person_id, user_text)
        self._observe_memory_correction(person_id, user_text)
        self._observe_cringe_event(person_id, user_text, monika_reply, stage)
        if self._nickname_source_allowed(semantic_user, monika_reply, stage):
            for nick in self._extract_nicknames_from_reply(monika_reply):
                self.propose_nickname(person_id, nick, f"U: {user_text[:160]} | M: {monika_reply[:220]}")
        if self._is_nickname_request(semantic_user):
            self._journal(person_id, "scene_turn", "active", stage or "NAME_PLAY", 0.0, f"Пользователь: {user_text[:180]} | Моника: {monika_reply[:240]}")
        self.conn.commit()

    def _repair_reply(self, person_id: str, user_text: str, reply: str, stage: str = "") -> str:
        text = str(reply or "").strip()
        semantic_user = self.normalize_for_intent(user_text)
        if self.is_memory_philosophy(semantic_user) and self._reply_has_memory_leakage(text):
            return "Нет, балда, удалить воспоминание так, будто его не было, я не могу. Я могу пометить этот момент как кринжовый или неловкий и не вытаскивать его без повода. Но он остаётся частью нашей истории — неприятно, зато честно."

        # Accept/reject — это реакция на кличку, а не просьба генерировать новые.
        # Без этой развилки «Ахаха, X норм» могло ошибочно превращаться в «X не называю».
        if self._is_reject_intent(semantic_user):
            rejected = self._extract_reaction_target(person_id, semantic_user, want="reject")
            if rejected:
                canonical = rejected["nickname"]
                return f"Поняла, {canonical} не называю."

        if self._is_accept_intent(semantic_user):
            accepted = self._extract_reaction_target(person_id, semantic_user, want="accept")
            if accepted:
                canonical = accepted["nickname"]
                if self._reply_is_nickname_list(text) or "не называ" in normalize_key(text) or self._is_nickname_request(semantic_user):
                    return f"О, принято. {canonical} оставляю как рабочую кличку, балда."

        if self._is_nickname_request(semantic_user):
            text = self._repair_nickname_list_if_needed(person_id, text)
        return text

    def _build_prompt_block(self, person_id: str, user_text: str, stage: str = "") -> str:
        semantic_user = self.normalize_for_intent(user_text)
        lines: List[str] = []
        if self.is_memory_philosophy(semantic_user):
            lines += ["### MEMORY_PHILOSOPHY", "- Тема сейчас про память/воспоминания/кринж, не про игры.", "- Не говори, что можешь физически удалить или стереть воспоминание.", "- Можно: пометить как кринжовое/неловкое/спорное и не вытаскивать без повода.", "- Не используй Elden Ring/Dark Souls/костры как метафору, если пользователь прямо не просит."]
        accepted = self._list_nicknames(person_id, ("accepted", "active"), 5)
        rejected = self._list_nicknames(person_id, ("rejected",), 8)
        if self._is_accept_intent(semantic_user):
            lines += ["### NICKNAME_REACTION", "- Пользователь принимает/одобряет кличку. Не придумывай новые клички без просьбы.", "- Коротко признай принятие: «принято» / «оставляю в списке». Не говори «не называю»." ]
        elif self._is_reject_intent(semantic_user):
            lines += ["### NICKNAME_REACTION", "- Пользователь запрещает кличку. Не спорь и не придумывай замену без прямой просьбы.", "- Коротко подтверди границу: «поняла, так не называю»." ]
        if accepted or rejected:
            lines.append("### SOCIAL_NICKNAMES")
            if accepted: lines.append("- Можно иногда использовать: " + ", ".join(r["nickname"] for r in accepted))
            if rejected: lines.append("- Не использовать клички: " + ", ".join(r["nickname"] for r in rejected))
        return "\n".join(lines)

    def is_memory_philosophy(self, text: str) -> bool:
        t = normalize_key(text)
        return any(h in t for h in MEMORY_PHILOSOPHY_HINTS)

    def _is_nickname_request(self, text: str) -> bool:
        t = normalize_key(text)
        return bool(re.search(r"\b(кличк[аиуойе]?|кличек|прозвищ[ае]?|прозвище|назови меня|как меня назовешь|как ты меня назовешь)\b", t) or (("еще" in t or "ещё" in t) and ("назови" in t or "клич" in t)))

    def _nickname_source_allowed(self, user_text: str, reply: str, stage: str = "") -> bool:
        st = normalize_key(stage)
        if "name_play" in st or "nickname" in st or self._is_nickname_request(user_text): return True
        return bool(re.match(r"^\s*(?:ладно|слушай|эй|ну что)\s*,\s*[А-ЯA-ZЁ][^,.!?]{2,45}\s*,", reply or ""))

    def _extract_nicknames_from_reply(self, reply: str) -> List[str]:
        text = re.sub(r"[😏😄😁😂🤣😉🙂🤔😈]+", " ", str(reply or ""))
        text = re.sub(r"\s+", " ", text).strip()
        candidates: List[str] = []
        candidates += re.findall(r"[\"«“]([^\"»”]{2,60})[\"»”]", text)
        first = re.split(r"[.!?]\s+", text, maxsplit=1)[0]
        if "," in first:
            candidates += first.split(",")
        m = re.match(r"^\s*(?:ладно|слушай|эй|ну что)\s*,\s*([^,.!?]{2,55})\s*,", text, re.I)
        if m: candidates.append(m.group(1))
        out, seen = [], set()
        for raw in candidates:
            nick = self._clean_nickname(raw)
            key = normalize_key(nick)
            if key and key not in seen and self._valid_nickname(nick):
                out.append(nick); seen.add(key)
        return out[:6]

    def _clean_nickname(self, raw: str) -> str:
        nick = str(raw or "").strip(" \t\r\n,.;:!?—–-\"'«»“”()[]")
        nick = re.sub(r"^(?:например|вот|тогда|будешь|будешь у меня|ты теперь|назову тебя|я назову тебя)\s+", "", nick, flags=re.I)
        return re.sub(r"\s+", " ", nick).strip()[:80]

    def _valid_nickname(self, nickname: str) -> bool:
        nick, norm = self._clean_nickname(nickname), normalize_key(nickname)
        if not norm or len(norm) < 3 or len(nick) > 60 or norm in OLD_NICKNAME_BLACKLIST: return False
        if any(f in norm for f in BAD_NICKNAME_FRAGMENTS): return False
        words = norm.split()
        if not (1 <= len(words) <= 5): return False
        if all(len(w) <= 2 for w in words): return False
        if re.search(r"\b(я|ты|он|она|мы|вы|они|меня|тебя|себя|это|тот|этот|как|что|где|когда)\b", norm): return False
        if re.search(r"\b(люблю|ненавижу|терпеть|могу|хочу|думаю|говорил|помню|помнить|знаю|знаешь)\b", norm): return False
        return True

    def propose_nickname(self, person_id: str, nickname: str, source_event: str = "") -> Optional[int]:
        nickname = self._clean_nickname(nickname)
        if not self._valid_nickname(nickname) or self._is_existing_or_rejected(person_id, nickname): return None
        cur = self.conn.cursor()
        try:
            cur.execute("""INSERT INTO social_nicknames (person_id,nickname,normalized,status,tone,source_event,created_at,last_used_at) VALUES (?, ?, ?, 'proposed', 'teasing', ?, ?, ?)""", (person_id, nickname, normalize_key(nickname), source_event[:500], now_ts(), now_ts()))
            self._log("nickname_proposed", person_id, nickname, "ok", source_event[:300])
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def _is_accept_intent(self, text: str) -> bool:
        t = normalize_key(text)
        return any(w in t for w in ACCEPT_WORDS) and not self._is_reject_intent(t)

    def _is_reject_intent(self, text: str) -> bool:
        t = normalize_key(text)
        return any(w in t for w in REJECT_WORDS)

    def _observe_nickname_reaction(self, person_id: str, user_text: str) -> None:
        t = normalize_key(user_text)
        if self._is_reject_intent(t):
            target = self._extract_reaction_target(person_id, t, "reject")
            if target: self._set_nickname_status(person_id, target["nickname"], "rejected", 0, 1, "nickname_reject")
            return
        if self._is_accept_intent(t):
            target = self._extract_reaction_target(person_id, t, "accept")
            if target: self._set_nickname_status(person_id, target["nickname"], "accepted", 1, 0, "nickname_accept")

    def _extract_reaction_target(self, person_id: str, user_text: str, want: str = "accept") -> Optional[Dict[str, Any]]:
        t = normalize_key(user_text)
        if want == "accept" and not self._is_accept_intent(t):
            return None
        if want == "reject" and not self._is_reject_intent(t):
            return None
        match = self.resolve_nickname_fuzzy(person_id, t)
        if match: return match
        if want == "accept": return self._latest_nickname(person_id, ("proposed",))
        if want == "reject": return self._latest_nickname(person_id, ("proposed", "accepted", "active"))
        return None

    def resolve_nickname_fuzzy(self, person_id: str, text: str, min_score: float = 0.78) -> Optional[Dict[str, Any]]:
        rows = self._list_nicknames(person_id, ("proposed", "accepted", "active", "rejected"), 80)
        if not rows: return None
        text_norm, tokens = normalize_key(text), normalize_key(text).split()
        best = None
        for row in rows:
            nick_norm = normalize_key(row["nickname"])
            score = similarity(nick_norm, text_norm)
            if nick_norm in text_norm: score = max(score, 0.97)
            n = max(1, len(nick_norm.split()))
            for wlen in range(max(1, n - 1), min(len(tokens), n + 2) + 1):
                for i in range(0, max(0, len(tokens) - wlen) + 1):
                    score = max(score, similarity(nick_norm, " ".join(tokens[i:i + wlen])))
            if best is None or score > best[0]: best = (score, row)
        if best and best[0] >= min_score:
            r = best[1]
            return {"id": r["id"], "person_id": r["person_id"], "nickname": r["nickname"], "normalized": r["normalized"], "status": r["status"], "score": best[0]}
        return None

    def _set_nickname_status(self, person_id: str, nickname: str, status: str, positive_delta: int = 0, negative_delta: int = 0, action: str = "nickname_update") -> None:
        self.conn.execute("""UPDATE social_nicknames SET status=?, last_used_at=?, positive_reactions=COALESCE(positive_reactions,0)+?, negative_reactions=COALESCE(negative_reactions,0)+? WHERE person_id=? AND normalized=?""", (status, now_ts(), int(positive_delta), int(negative_delta), person_id, normalize_key(nickname)))
        self._log(action, person_id, nickname, "ok", f"status={status}")

    def _list_nicknames(self, person_id: str, statuses: Sequence[str] = ("proposed",), limit: int = 20) -> List[sqlite3.Row]:
        qs = ",".join("?" for _ in statuses)
        cur = self.conn.cursor()
        cur.execute(f"SELECT * FROM social_nicknames WHERE person_id=? AND status IN ({qs}) ORDER BY id DESC LIMIT ?", (person_id, *statuses, int(limit)))
        return list(cur.fetchall())

    def _latest_nickname(self, person_id: str, statuses: Sequence[str]) -> Optional[Dict[str, Any]]:
        rows = self._list_nicknames(person_id, statuses, 1)
        if not rows: return None
        r = rows[0]
        return {"id": r["id"], "person_id": r["person_id"], "nickname": r["nickname"], "normalized": r["normalized"], "status": r["status"], "score": 0.0}

    def _is_existing_or_rejected(self, person_id: str, nickname: str) -> bool:
        norm = normalize_key(nickname)
        if norm in OLD_NICKNAME_BLACKLIST: return True
        cur = self.conn.cursor()
        cur.execute("SELECT status FROM social_nicknames WHERE person_id=? AND normalized=? LIMIT 1", (person_id, norm))
        return cur.fetchone() is not None

    def _remove_rejected_nickname_mentions(self, person_id: str, reply: str, keep: str = "") -> str:
        text = str(reply or "")
        keep_norm = normalize_key(keep)
        for row in self._list_nicknames(person_id, ("rejected",), 50):
            if keep_norm and normalize_key(row["nickname"]) == keep_norm:
                continue
            text = re.sub(re.escape(row["nickname"]), "", text, flags=re.I)
        return re.sub(r"\s{2,}", " ", text).strip()

    def _reply_acknowledges_reject(self, reply: str, nickname: str) -> bool:
        r, n = normalize_key(reply), normalize_key(nickname)
        return ("не называ" in r or "не буду" in r or "поняла" in r) and (n in r or similarity(n, r) > 0.70)

    def _reply_is_nickname_list(self, reply: str) -> bool:
        text = str(reply or "").strip()
        extracted = self._extract_nicknames_from_reply(text)
        if len(extracted) >= 2:
            return True
        first_sentence = re.split(r"[.!?]\s+", text, maxsplit=1)[0]
        return first_sentence.count(",") >= 2 and len(first_sentence) <= 180

    def _repair_nickname_list_if_needed(self, person_id: str, reply: str) -> str:
        extracted = self._extract_nicknames_from_reply(reply)
        if not extracted: return reply
        bad = 0
        for nick in extracted:
            if not self._valid_nickname(nick) or normalize_key(nick) in OLD_NICKNAME_BLACKLIST or self._is_existing_or_rejected(person_id, nick): bad += 1
        return ", ".join(self._fresh_nickname_list(person_id, 4)) + ". 😏" if bad else reply

    def _fresh_nickname_list(self, person_id: str, count: int = 4) -> List[str]:
        out = [n for n in FRESH_NICKNAME_POOL if not self._is_existing_or_rejected(person_id, n)]
        return (out + FRESH_NICKNAME_POOL)[:count]

    def _observe_user_preferences(self, person_id: str, user_text: str) -> None:
        for subject, stance, source in self._extract_user_preferences(user_text):
            self._upsert_memory_item(person_id, "user_preference", subject, "likes" if stance == "likes" else "dislikes", subject, stance, "candidate", 0.78, source)

    def _extract_user_preferences(self, text: str) -> List[Tuple[str, str, str]]:
        raw, results = str(text or ""), []
        for pat in [r"(?:^|[.!?]\s*)(?:я\s+)?(?:люблю|обожаю)\s+([^.!?]+)", r"(?:^|[.!?]\s*)мне\s+(?:нравится|нравятся)\s+([^.!?]+)"]:
            for m in re.finditer(pat, raw, flags=re.I):
                for obj in split_objects(m.group(1)): results.append((obj, "likes", m.group(0).strip()))
        for pat in [r"(?:^|[.!?]\s*)(?:я\s+)?(?:терпеть\s+не\s+могу|ненавижу|не\s+люблю)\s+([^.!?]+)", r"(?:^|[.!?]\s*)([^.!?]{2,60}?)\s+я\s+(?:терпеть\s+не\s+могу|ненавижу|не\s+люблю)(?:[.!?]|$)"]:
            for m in re.finditer(pat, raw, flags=re.I):
                for obj in split_objects(m.group(1)): results.append((obj, "dislikes", m.group(0).strip()))
        dedup = {}
        for subj, stance, source in results:
            key = (normalize_key(subj), stance)
            if key[0] and key not in dedup: dedup[key] = (subj, stance, source)
        return list(dedup.values())[:8]

    def _upsert_memory_item(self, person_id: str, kind: str, subject: str, predicate: str, value: str, stance: str, status: str, confidence: float, source_text: str) -> None:
        subject = self._clean_fact_subject(subject)
        if not subject: return
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM autonomous_memory_items WHERE person_id=? AND kind=? AND subject=? AND stance=? LIMIT 1", (person_id, kind, subject, stance))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE autonomous_memory_items SET predicate=?, value=?, status=?, confidence=MAX(confidence, ?), source_text=?, updated_at=? WHERE id=?", (predicate, value, status, confidence, source_text[:500], now_ts(), row["id"]))
        else:
            cur.execute("""INSERT INTO autonomous_memory_items (person_id,kind,subject,predicate,value,stance,status,confidence,source_text,created_at,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (person_id, kind, subject, predicate, value, stance, status, confidence, source_text[:500], now_ts(), now_ts()))
        self._log("fact_add", person_id, subject, "ok", f"{kind}:{stance}")

    def _clean_fact_subject(self, subject: str) -> str:
        s = str(subject or "").strip(" \t\r\n,.;:!?—–-\"'«»“”()[]")
        s = re.sub(r"^(?:а|но|и|вот|это|просто)\s+", "", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip()
        norm = normalize_key(s)
        if not norm or len(norm) < 2 or len(norm) > 60 or any(x in norm for x in ("память", "воспомин", "клич", "факт", "задач")): return ""
        return s

    def _observe_memory_correction(self, person_id: str, user_text: str) -> None:
        t = normalize_key(user_text)
        if re.search(r"\b(я такого не говорил|не говорил что|не говорила что|это неправда|ты придумала|ты перепутала)\b", t):
            self.conn.execute("INSERT INTO memory_corrections (person_id,correction_type,text,status,created_at) VALUES (?, 'user_denial', ?, 'candidate', ?)", (person_id, str(user_text)[:500], now_ts()))
            self._log("memory_correction", person_id, "", "ok", str(user_text)[:300])

    def _observe_cringe_event(self, person_id: str, user_text: str, monika_reply: str, stage: str = "") -> None:
        if self._is_explicit_cringe_event(user_text):
            self._journal(person_id, "cringe_memory", "cringe", stage or "MEMORY_PHILOSOPHY", 0.7, f"Кринж/стыдный момент: {user_text[:240]}")
            self._log("cringe_mark", person_id, "", "ok", user_text[:300])

    def _is_explicit_cringe_event(self, text: str) -> bool:
        if "?" in str(text or ""): return False
        t = normalize_key(text)
        return bool(re.search(r"\b(это был|это была|это)\s+(кринж|кринжовый|стыдный|неловкий)\s+момент\b", t) or re.search(r"\b(запомни|пометь|оставь)\s+.*\b(как|что это)\s+(кринж|стыд|неловк)", t) or re.search(r"\bмне стыдно за (этот|тот) момент\b", t))

    def _journal(self, person_id: str, event_type: str, status: str, stage: str, cringe_score: float, summary: str) -> None:
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM monika_experience_journal WHERE person_id=? AND event_type=? AND summary=? LIMIT 1", (person_id, event_type, summary[:500]))
        if cur.fetchone(): return
        cur.execute("INSERT INTO monika_experience_journal (person_id,event_type,status,stage,cringe_score,summary,created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (person_id, event_type, status, stage or "", float(cringe_score), summary[:500], now_ts()))

    def _reply_has_memory_leakage(self, reply: str) -> bool:
        r = normalize_key(reply)
        return bool(re.search(r"\b(elden ring|dark souls|элден ринг|дарк соулс|костер|костёр|скелет|щит|откат)\b", r) or re.search(r"\b(могу|можно|давай)\s+(забыть|удалить|стереть)\b", r) or "забыть про" in r or "только на пару минут" in r)

    def _log(self, action_type: str, person_id: str, target: str, status: str, detail: str = "") -> None:
        try:
            self.conn.execute("INSERT INTO memory_action_log (action_type,person_id,target,status,detail,created_at) VALUES (?, ?, ?, ?, ?, ?)", (action_type, person_id, target, status, str(detail or "")[:500], now_ts()))
        except sqlite3.Error:
            pass
