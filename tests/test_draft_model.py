import httpx
import pytest
from pydantic import ValidationError

from app.db import connect, migrate
from app.drafter import DraftGenerator
from app.model_contract import DraftDecision
from app.repository import NormalizedSignal, Repository


SOURCE_TEXT = "销售获客讨论\n团队正在筛选销售线索，人工筛选效率低"


def valid_draft() -> dict[str, str]:
    return {
        "body": "你提到人工筛选效率低。我们正在研究 B2B 销售 Agent 的线索流程。你们每周需要筛选多少条线索？",
        "source_snippet": "人工筛选效率低",
        "research_purpose_sentence": "我们正在研究 B2B 销售 Agent 的线索流程。",
        "diagnostic_question": "你们每周需要筛选多少条线索？",
    }


class DraftClient:
    provider = "openai-compatible"
    model = "draft-model"

    def __init__(self, outcome):
        self.outcome = outcome

    def generate_draft(self, *, source_text):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome, {"total_tokens": 17}


def draft_facts(tmp_path):
    connection = connect(tmp_path / "draft.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili",
            external_source_id="draft-source",
            source_title="销售获客讨论",
            source_url="https://www.bilibili.com/video/draft-source",
            external_comment_id="draft-comment",
            comment_url="https://www.bilibili.com/video/draft-source#reply",
            author_public_id="draft-lead",
            body="团队正在筛选销售线索，人工筛选效率低",
        ),
    ).signal_id
    return connection, repository, run_id, signal_id


def test_draft_contract_requires_verbatim_research_sentence_and_one_question():
    parsed = DraftDecision.model_validate(
        valid_draft(), context={"source_text": SOURCE_TEXT}
    )
    assert len(parsed.body) <= 180

    for invalid in (
        valid_draft() | {"source_snippet": "不存在的客户预算"},
        valid_draft() | {"research_purpose_sentence": "我们提供一套现成工具。"},
        valid_draft() | {"diagnostic_question": "请尽快联系我们。"},
        valid_draft() | {"source_snippet": " "},
        valid_draft() | {"invented": "not allowed"},
    ):
        with pytest.raises(ValidationError):
            DraftDecision.model_validate(invalid, context={"source_text": SOURCE_TEXT})


def test_draft_generator_persists_generated_success_and_never_human_edit(tmp_path):
    connection, repository, run_id, signal_id = draft_facts(tmp_path)

    result = DraftGenerator(repository, DraftClient(valid_draft())).generate(
        run_id, signal_id
    )
    row = connection.execute(
        "SELECT provider, model, prompt_version, draft_kind, body, status, "
        "activity_session_id, error_code FROM draft_runs WHERE draft_run_id = ?",
        (result.draft_run_id,),
    ).fetchone()

    assert result.status == "SUCCEEDED"
    assert tuple(row) == (
        "openai-compatible",
        "draft-model",
        "DISCOVERY_DRAFT_V1",
        "GENERATED",
        valid_draft()["body"],
        "SUCCEEDED",
        None,
        None,
    )
    connection.close()


@pytest.mark.parametrize(
    ("client", "error_code"),
    [
        (None, "MODEL_NOT_CONFIGURED"),
        (DraftClient({"body": "not strict"}), "MODEL_OUTPUT_INVALID"),
        (
            DraftClient(
                httpx.ReadTimeout(
                    "timeout",
                    request=httpx.Request("POST", "https://model.invalid"),
                )
            ),
            "MODEL_UNAVAILABLE",
        ),
    ],
)
def test_draft_generator_fails_closed_and_appends_no_body(tmp_path, client, error_code):
    connection, repository, run_id, signal_id = draft_facts(tmp_path)

    result = DraftGenerator(repository, client).generate(run_id, signal_id)
    row = connection.execute(
        "SELECT draft_kind, body, status, error_code FROM draft_runs "
        "WHERE draft_run_id = ?",
        (result.draft_run_id,),
    ).fetchone()

    assert (result.status, result.error_code) == ("FAILED", error_code)
    assert tuple(row) == ("GENERATED", None, "FAILED", error_code)
    connection.close()
