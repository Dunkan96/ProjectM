# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

try:
    import websockets
except ImportError as exc:
    raise SystemExit("Missing dependency: python -m pip install websockets") from exc

from attention_stream_adapter import AttentionStreamAdapter
from streamerbot_event_normalizer import normalize_streamerbot_event

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "streamerbot_attention_config.json"
LOGS = ROOT / "Logs"
LOGS.mkdir(exist_ok=True)


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {
        "streamerbot_ws": {
            "host": "127.0.0.1",
            "port": 8081,
            "endpoint": "/",
            "password": "",
            "subscribe": {
                "Twitch": ["ChatMessage", "Follow", "Cheer", "Sub", "ReSub", "GiftSub", "GiftBomb", "Raid", "RewardRedemption", "StreamUpdate", "UserTimedOut", "UserBanned"],
                "Obs": ["Connected", "Disconnected", "SceneChanged", "StreamingStarted", "StreamingStopped", "RecordingStarted", "RecordingStopped", "Event"],
            },
        },
        "attention": {"digest_limit": 8},
        "moderation": {"mode": "dry_run"},
    }


def ws_url(cfg: dict[str, Any]) -> str:
    ws_cfg = cfg.get("streamerbot_ws") or cfg.get("streamerbot") or {}
    host = ws_cfg.get("host", "127.0.0.1")
    port = int(ws_cfg.get("port", 8081))
    endpoint = str(ws_cfg.get("endpoint", "/") or "/")
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return f"ws://{host}:{port}{endpoint}"


def subscribe_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    ws_cfg = cfg.get("streamerbot_ws") or cfg.get("streamerbot") or {}
    events = ws_cfg.get("subscribe") or {
        "Twitch": ["ChatMessage", "Follow", "Cheer", "Sub", "ReSub", "GiftSub", "GiftBomb", "Raid", "RewardRedemption", "StreamUpdate", "UserTimedOut", "UserBanned"],
        "Obs": ["Connected", "Disconnected", "SceneChanged", "StreamingStarted", "StreamingStopped", "RecordingStarted", "RecordingStopped", "Event"],
    }
    return {"request": "Subscribe", "id": "monika-attention-subscribe", "events": events}


async def send_json(ws: Any, payload: dict[str, Any]) -> None:
    await ws.send(json.dumps(payload, ensure_ascii=False))


async def run_bridge(cfg: dict[str, Any]) -> None:
    attention = AttentionStreamAdapter(config=cfg)
    url = ws_url(cfg)
    mod_cfg = cfg.get("moderation") or {}
    print(f"[connect] {url}")
    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        await send_json(ws, {"request": "GetInfo", "id": "monika-get-info"})
        sub = subscribe_payload(cfg)
        print("[subscribe]", json.dumps(sub.get("events", {}), ensure_ascii=False))
        await send_json(ws, sub)
        print(f"[mode] moderation: {mod_cfg.get('mode', 'dry_run')}")

        async for msg in ws:
            try:
                raw = json.loads(msg)
            except Exception:
                print("[raw]", str(msg)[:300])
                continue

            append_jsonl(LOGS / "streamerbot_raw_events.jsonl", raw)

            if raw.get("id") in {"monika-get-info", "monika-attention-subscribe"}:
                print("[server]", json.dumps(raw, ensure_ascii=False, default=str)[:600])
                continue

            ev = normalize_streamerbot_event(raw)
            source = (ev.event_source or "").casefold()
            typ = ev.event_type or ""

            if source == "twitch" and typ == "ChatMessage":
                data = ev.to_attention_data()
                raw_data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
                if "badges" in raw_data:
                    data["badges"] = raw_data.get("badges")
                if "role" in raw_data:
                    data["role"] = raw_data.get("role")
                decision = attention.enqueue_twitch_message(data, raw)
                print(f"[chat:{decision.bucket}] {decision.user_name}: {decision.text} score={decision.score:.2f} action={decision.action}")
                if decision.bucket == "safety":
                    reason = (decision.safety_json or {}).get("risk") or ",".join(decision.reasons)
                    print(f"[moderation:dry_run] {decision.action} user={decision.user_name} reason={reason}")
            elif source == "obs":
                text = ev.text or typ
                print(f"[obs] {text}")
            elif source or typ:
                print(f"[event] {ev.event_source}.{typ}")


def inject_creator(text: str) -> None:
    decision = AttentionStreamAdapter(config=load_config()).enqueue_creator_event(text)
    print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2, default=str))


def print_digest(consume: bool = False) -> None:
    cfg = load_config()
    limit = int((cfg.get("attention") or {}).get("digest_limit", 8))
    digest = AttentionStreamAdapter(config=cfg).build_digest(limit=limit, consume=consume)
    print(digest or "<empty>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inject-creator")
    ap.add_argument("--digest", action="store_true")
    ap.add_argument("--consume", action="store_true")
    args = ap.parse_args()

    if args.inject_creator:
        inject_creator(args.inject_creator)
        return
    if args.digest:
        print_digest(args.consume)
        return

    try:
        asyncio.run(run_bridge(load_config()))
    except KeyboardInterrupt:
        print("\n[stop]")


if __name__ == "__main__":
    main()
