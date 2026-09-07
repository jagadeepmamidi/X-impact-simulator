import json
from types import SimpleNamespace

from app import groq_client


def test_vision_request_fits_small_output_budget(monkeypatch):
    """Reproduce the provider's 1000 OTPM limit without a paid network call."""
    def create(**request):
        budget = request.get('max_completion_tokens', 1189)
        assert budget <= 1000, 'Provider rejects the default expected output size'
        assert request.get('reasoning_effort') == 'none'
        assert request['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/png')
        content = json.dumps({'topics': ['AI tools'], 'visual_hook': 0.7})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(groq_client, '_client', lambda: client)
    monkeypatch.setattr(groq_client.settings, 'groq_vision_model', 'qwen/qwen3.6-27b')
    result = groq_client.groq_vision_content('', ['data:image/png;base64,fixture'], 'One test image')
    assert result is not None
    assert result.source == 'groq'
    assert result.topics == ['AI tools']
