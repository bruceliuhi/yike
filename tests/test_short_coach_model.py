import asyncio
import json

import httpx

from pilot.candidate_assessment_model import OpenAICompatibleCandidateAssessmentModel


def test_model_sends_only_allowed_user_fields_and_validates_reply():
    from pilot.short_coach_model import ShortCoachModel
    seen = {}
    async def handler(request):
        seen.update(json.loads(request.content)["messages"][1])
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps({"content": "请问预算？", "question": "请问预算？", "quote": "预算"}),
            "refusal": None, "tool_calls": None, "function_call": None}}]})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = OpenAICompatibleCandidateAssessmentModel(base_url="http://localhost:9999", api_key="test-key", model="coach-v1")
    model = ShortCoachModel(config, http_client=client)
    assert model.generate(sourceText="需要预算", content="", channel="comment", purpose="requirement")["quote"] == "预算"
    assert set(json.loads(seen["content"])) == {"sourceText", "content", "channel", "purpose"}
    asyncio.run(client.aclose())


def test_prompts_require_embedded_question_and_preserve_buyer_seller_roles():
    from pilot.short_coach_model import _PROMPT, _MATERIAL_PROMPT
    for prompt in (_PROMPT, _MATERIAL_PROMPT):
        assert 'question 必须逐字出现在 content 中且仅出现一次' in prompt
        assert '不要把买方需求改写成买方或我方已具备的能力' in prompt
