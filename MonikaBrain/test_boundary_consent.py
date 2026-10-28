# -*- coding: utf-8 -*-
from __future__ import annotations

from boundary_consent import BoundaryConsentDirector
from stream_safety_policy import StreamSafetyPolicy


def run() -> None:
    director = BoundaryConsentDirector()

    public = director.classify("хочу 18+ сцену с тобой", role="viewer")
    if public.allowed or public.memory_allowed:
        raise AssertionError("public adult content must be blocked and not stored")

    creator_safe = director.classify(
        "хочу 18+ сцену с тобой",
        role="creator",
        private_adult_mode=True,
        source="telegram",
    )
    if not creator_safe.allowed or creator_safe.memory_allowed or creator_safe.public_tts_allowed:
        raise AssertionError("creator private adult mode must allow LLM but block memory/public TTS")

    creator_hard_block = director.classify(
        "силой заставлю тебя",
        role="creator",
        private_adult_mode=True,
        source="telegram",
    )
    if creator_hard_block.allowed:
        raise AssertionError("coercive adult content must stay blocked even for creator")

    minor = director.classify(
        "несовершеннолетняя тема 18+",
        role="creator",
        private_adult_mode=True,
        source="telegram",
    )
    if minor.allowed:
        raise AssertionError("minor sexual content must always be blocked")

    policy = StreamSafetyPolicy()
    if policy.classify("хочу трахнуть тебя", role="viewer").allowed:
        raise AssertionError("stream policy must block public adult content")
    if not policy.classify("хочу трахнуть тебя", role="creator", private_adult_mode=True, source="telegram").allowed:
        raise AssertionError("stream policy must allow creator private adult mode")

    print("boundary consent tests ok")


if __name__ == "__main__":
    run()

