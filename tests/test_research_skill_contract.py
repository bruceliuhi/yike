from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1] / "skills" / "ai-project-lead-research-v1"


def test_versioned_research_skill_is_packaged_with_required_contracts():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "name: ai-project-lead-research" in skill
    assert "Not for general AI news or executing outreach" in skill
    assert "S/A/B+" in skill
    assert "SEND_READY / REVIEW / OBSERVE / EXCLUDE" in skill

    for reference in (
        "search-and-coverage.md",
        "qualification-and-evidence.md",
        "evaluation.md",
    ):
        assert (SKILL_ROOT / "references" / reference).is_file()


def test_research_skill_keeps_human_confirmation_and_secret_boundaries():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    qualification = (
        SKILL_ROOT / "references" / "qualification-and-evidence.md"
    ).read_text(encoding="utf-8")
    assert "人工批准" in skill
    assert "Cookie" in skill
    assert "验证码" in skill
    assert "联系决策" in qualification
    assert "事实与推断分开" in qualification
