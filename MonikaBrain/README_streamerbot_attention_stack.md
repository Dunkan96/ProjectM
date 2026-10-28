# Monika Streamer.bot Attention Stack v1

Safe by default:
- Reads Twitch chat from Streamer.bot WebSocket.
- Reads OBS events from Streamer.bot WebSocket.
- Scores events before Monika sees them.
- Records moderation candidates in dry-run mode.
- Does not write to Twitch.
- Does not ban/timeout/VIP anyone.
- Does not patch console_chat.py.

Run:
  python -m pip install websockets
  python streamerbot_attention_bridge.py

Inspect:
  python inspect_attention.py
  python inspect_moderation.py
  python streamerbot_attention_bridge.py --digest

Test creator event:
  python streamerbot_attention_bridge.py --inject-creator "Моника, проверь чат"

Real moderation requires:
- manually configured Streamer.bot actions,
- action names in streamerbot_attention_config.json,
- moderation.mode = "execute".
Keep dry_run until several real tests pass.
