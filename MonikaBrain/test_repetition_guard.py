from repetition_guard import RepetitionGuard


def test_user_banned_phrase_is_blocked():
    guard = RepetitionGuard()
    session = {}
    guard.update_session_from_user(
        session,
        'Не произноси больше фразу "Но если это твой способ признаться, то может я тоже кое-что сделаю"',
    )
    verdict = guard.assess(
        "Но если это твой способ признаться, то может я тоже кое-что сделаю.",
        [],
        session,
    )
    assert not verdict.ok
    assert "banned_phrase" in verdict.reasons


def test_similar_recent_reply_is_blocked():
    guard = RepetitionGuard()
    session = {}
    history = [
        {"role": "assistant", "content": "Хорошо, тогда слушай внимательно. Я включаю режим смелой Моники."}
    ]
    verdict = guard.assess(
        "Хорошо, тогда слушай внимательно. Я включаю режим смелой Моники.",
        history,
        session,
    )
    assert not verdict.ok
    assert "similar_to_recent_reply" in verdict.reasons


def test_no_emoji_session_strips_emoji():
    guard = RepetitionGuard()
    session = {}
    guard.update_session_from_user(session, "хватит этих смайликов")
    verdict = guard.assess("Ладно, без балагана 😏", [], session)
    assert not verdict.ok
    assert guard.sanitize("Ладно, без балагана 😏", session) == "Ладно, без балагана"


if __name__ == "__main__":
    test_user_banned_phrase_is_blocked()
    test_similar_recent_reply_is_blocked()
    test_no_emoji_session_strips_emoji()
    print("RepetitionGuard tests passed")
