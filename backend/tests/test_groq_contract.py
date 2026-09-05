import json
from types import SimpleNamespace

from app.groq_client import groq_persona_reactions
from app.schemas import ContentFeatures, Persona


def _persona(pid: str) -> Persona:
    return Persona(
        id=pid,
        name=pid,
        role="tester",
        interests=["testing"],
        expertise=0.5,
        activity_level=0.5,
        novelty_seeking=0.5,
        promotional_tolerance=0.5,
        reply_tendency=0.2,
        repost_tendency=0.2,
        dwell_tendency=0.5,
        negative_sensitivity=0.2,
        evidence_demand=0.5,
    )


def _fake_client(payload: dict):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
    )
    completions = SimpleNamespace(create=lambda **_kwargs: response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_partial_persona_response_is_rejected(monkeypatch) -> None:
    import app.groq_client as client

    monkeypatch.setattr(
        client,
        "_client",
        lambda: _fake_client({"reactions": [{"persona_id": "a"}]}),
    )

    result = groq_persona_reactions([_persona("a"), _persona("b")], ContentFeatures())

    assert result is None


def test_complete_persona_response_is_returned_in_pack_order(monkeypatch) -> None:
    import app.groq_client as client

    monkeypatch.setattr(
        client,
        "_client",
        lambda: _fake_client(
            {"reactions": [{"persona_id": "b"}, {"persona_id": "a"}]}
        ),
    )

    result = groq_persona_reactions([_persona("a"), _persona("b")], ContentFeatures())

    assert result is not None
    assert [reaction.persona_id for reaction in result] == ["a", "b"]
