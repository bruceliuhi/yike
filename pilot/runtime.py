"""Ordinary Web runtime composition; construction grants no source capability."""
from __future__ import annotations

import os
from collections.abc import Mapping

from fastapi import FastAPI

from pilot.candidate_assessment_model import AssessmentModelError, OpenAICompatibleCandidateAssessmentModel
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.candidate_review import CandidateReviewStore
from pilot.contact_drafts import ContactDraftStore
from pilot.materials import MaterialStore
from pilot.material_model import MaterialExtractionModel
from pilot.monitor_plans import MonitorPlanStore
from pilot.outreach_queue import OutreachQueueStore
from pilot.db import PilotDatabase
from pilot.execution_runtime import ExecutionRuntime
from pilot.foreground_collection import configured_collection_policy
from pilot.research_strategies import ResearchStrategyStore
from pilot.reply_store import ReplyEventStore
from pilot.signed_replies import SignedReplyStore
from pilot.store import PilotStore
from pilot.web import build_app


_ASSESSMENT_CONFIGURATION = (
    "YIKE_PILOT_ASSESSMENT_BASE_URL",
    "YIKE_PILOT_ASSESSMENT_API_KEY",
    "YIKE_PILOT_ASSESSMENT_MODEL",
)


def _assessment_model(environment: Mapping[str, str]):
    values = tuple(environment.get(name, "") for name in _ASSESSMENT_CONFIGURATION)
    present = tuple(bool(value.strip()) for value in values)
    if not any(present):
        return None
    if not all(present):
        raise RuntimeError("invalid_assessment_configuration")
    try:
        return OpenAICompatibleCandidateAssessmentModel(
            base_url=values[0], api_key=values[1], model=values[2]
        )
    except AssessmentModelError:
        pass
    raise RuntimeError("invalid_assessment_configuration")


def build_runtime_app(
    database: PilotDatabase,
    *,
    auth_secret: str,
    dev_login: bool = False,
    environment: Mapping[str, str] | None = None,
) -> FastAPI:
    environment = os.environ if environment is None else environment
    if environment.get("YIKE_PILOT_ADMIN_DATABASE_URL", "").strip():
        raise RuntimeError("admin_database_url_forbidden_in_web_runtime")

    model = _assessment_model(environment)
    store = PilotStore(database)
    strategies = ResearchStrategyStore(database)
    runtime = ExecutionRuntime(database, strategy_resolver=strategies.resolve,
                               capability_check=configured_collection_policy(environment))
    ingestion = CandidateIngestionStore(database, execution_runtime=runtime)
    review = CandidateReviewStore(
        database,
        model=model,
        strategy_resolver=strategies.resolve,
        strategy_snapshot_reader=strategies.read_snapshot,
    )
    replies = ReplyEventStore(database)
    drafts = ContactDraftStore(database)
    outreach_platforms = frozenset(filter(None, (v.strip() for v in
        environment.get('YIKE_PILOT_OUTREACH_PLATFORMS','').split(','))))
    if outreach_platforms - {'BILIBILI','DOUYIN','XIAOHONGSHU','ZHIHU'}:
        raise RuntimeError('invalid_outreach_platform_configuration')
    queue = OutreachQueueStore(database, drafts, runtime, outreach_platforms)
    replies.signed = SignedReplyStore(queue, replies)
    return build_app(
        store,
        auth_secret=auth_secret,
        dev_login=dev_login,
        execution_runtime=runtime,
        candidate_ingestion=ingestion,
        candidate_review=review,
        research_strategies=strategies,
        monitor_plans=MonitorPlanStore(database, strategy_resolver=strategies.resolve),
        reply_store=replies,
        contact_drafts=drafts,
        materials=MaterialStore(database, model=MaterialExtractionModel(model) if model is not None else None),
        outreach_queue=queue,
    )
