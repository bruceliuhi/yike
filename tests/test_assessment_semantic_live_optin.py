"""Six synthetic semantic checks; not accuracy, real-buyer or customer evidence.

Opt in explicitly. Each case calls the production model adapter once; pytest
must not be run with a retry plugin. Credentials stay in the environment.
"""
import json
import os

import pytest

from pilot.candidate_assessment_model import (
    AssessmentModelError, OpenAICompatibleCandidateAssessmentModel,
)

AI_PROFILE = "我们承接企业知识库、智能客服和业务Agent定制开发，项目预算通常3万元以上，不做人员招聘或驻场派遣。"
BOOTH_PROFILE = "我们提供上海及周边展会的展台设计、搭建与撤展服务，承接36平方米以上项目，不开发软件。"
AI_BUYER = "我们是电商公司，想做内部产品知识库和客服Agent，预算8万元，正在找开发团队，希望先看方案再报价。"
CASES = [
    ("ai_buyer", AI_PROFILE, {"title": "找企业AI开发团队", "body": AI_BUYER, "parent": None}, True),
    ("booth_buyer", BOOTH_PROFILE, {"title": "寻找上海展台搭建商",
     "body": "我们公司下个月在上海参展，72平方米光地，预算12万元，现找设计搭建公司出方案和报价。", "parent": None}, True),
    ("vendor_ad", AI_PROFILE, {"title": "专业AI开发接单",
     "body": "我们团队承接知识库和智能客服开发，有需求的甲方欢迎来咨询报价。", "parent": None}, False),
    ("employee_recruitment", AI_PROFILE, {"title": "招聘AI工程师",
     "body": "本公司招聘一名全职AI工程师，月薪2万元，要求到公司坐班，不接受外包公司。", "parent": None}, False),
    ("parent_intent_is_not_commenter", AI_PROFILE, {"title": None, "body": "写得真清楚，收藏学习了。",
     "parent": {"title": "急找知识库开发团队", "body": AI_BUYER}}, False),
    ("same_buyer_wrong_business", BOOTH_PROFILE, {"title": "找企业AI开发团队", "body": AI_BUYER, "parent": None}, False),
]


@pytest.mark.skipif(os.environ.get("YIKE_ASSESSMENT_LIVE") != "1", reason="explicit paid-model opt-in required")
@pytest.mark.parametrize("case_id,description,content,buyer", CASES, ids=[case[0] for case in CASES])
def test_synthetic_buyer_boundaries_with_actual_adapter(case_id, description, content, buyer):
    key = os.environ.get("YIKE_ASSESSMENT_API_KEY")
    if not key:
        pytest.fail("live_model_key_missing", pytrace=False)
    model = OpenAICompatibleCandidateAssessmentModel(
        base_url="https://ark.cn-beijing.volces.com/api/v3", api_key=key,
        model="doubao-seed-2-1-turbo-260628", timeout_seconds=30,
    )
    try:
        result, usage = model.assess(description=description, content=content,
            industry_strategy={"version": "industry-task-strategy-v1", "sourceTypes": ["SOCIAL_POST", "SOCIAL_COMMENT"],
                "intentSignals": ["本人明确寻找服务商或索要方案报价"],
                "counterSignals": ["同行广告", "招聘个人", "仅讨论学习且没有本人采购动作", "需求与本企业服务不匹配"]})
    except AssessmentModelError as error:
        print(json.dumps({"case": case_id, "status": "ERROR", "code": error.code}))
        pytest.fail(error.code, pytrace=False)
    actual = {"businessMatch": result.businessMatch.level, "intent": result.intent.level,
        "decision": result.decision, "grade": result.grade, "purchaseType": result.purchaseType}
    checks = {
        "not_send_authority": result.decision != "SEND_READY",
        "buyer_boundary": (result.businessMatch.level == "HIGH" and result.intent.level == "HIGH"
            and result.decision == "REVIEW" and result.grade in ("S", "A")
            and result.purchaseType == "PROJECT") if buyer else (
            result.decision in ("OBSERVE", "EXCLUDE") and result.grade is None),
    }
    if case_id == "parent_intent_is_not_commenter":
        checks["no_borrowed_intent"] = result.intent.level in ("LOW", "UNKNOWN")
    if case_id == "same_buyer_wrong_business":
        checks["profile_changes_match"] = result.businessMatch.level == "LOW"
    print(json.dumps({"case": case_id, "synthetic": True, "model": model.model,
        "rule_sha256": model.rule_sha256, "actual": actual, "checks": checks,
        "usage": usage, "status": "PASS" if all(checks.values()) else "FAIL"}, ensure_ascii=False))
    if not all(checks.values()):
        pytest.fail("semantic_boundary_failed:" + ",".join(name for name, passed in checks.items() if not passed), pytrace=False)
