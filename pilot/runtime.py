"""Ordinary Web runtime composition; construction grants no source capability."""
from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from pilot.candidate_assessment_model import AssessmentModelError, OpenAICompatibleCandidateAssessmentModel
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.candidate_review import CandidateReviewStore
from pilot.contact_drafts import ContactDraftStore
from pilot.short_coach import ShortCoachService
from pilot.short_coach_model import ShortCoachModel
from pilot.followup_service import FollowupService
from pilot.opportunity_brief import OpportunityBriefService
from pilot.materials import MaterialStore
from pilot.material_model import MaterialExtractionModel
from pilot.monitor_plans import MonitorPlanStore
from pilot.monitor_runtime import MonitorRuntime
from pilot.outreach_queue import OutreachQueueStore
from pilot.db import PilotDatabase
from pilot.execution_runtime import ExecutionRuntime
from pilot.foreground_collection import configured_collection_policy
from pilot.research_strategies import ResearchStrategyStore
from pilot.research_runtime_config import (research_configuration, public_research_policy,
    public_research_snapshot, configured_research_policy, configured_research_snapshot)
from pilot.research_quote import ResearchQuoteService
from pilot.research_execution import ResearchExecutionService
from pilot.research_resources import ResearchResourceStore
from pilot.research_candidates import ResearchCandidateStore
from pilot.research_assessment import ResearchAssessmentRunner
from pilot.research_orchestrator import ResearchOrchestrator
from pilot.research_runtime import ResearchRuntimeService
from pilot.research_effect_journal import ResearchEffectJournal
from pilot.dynamic_research_candidates import DynamicResearchCandidateStore
from pilot.dynamic_research_runtime import DynamicResearchRuntimeService
from pilot.reply_store import ReplyEventStore
from pilot.signed_replies import SignedReplyStore
from pilot.search_suggestion_model import SearchSuggestionError
from pilot.search_suggestion_process import ProcessSearchSuggestionModel
from pilot.search_suggestion_service import SearchSuggestionService
from pilot.search_suggestions import SearchSuggestionStore
from pilot.store import PilotStore
from pilot.web import build_app
from pilot.aliyun_sms import configured_sms_sender


_ASSESSMENT_CONFIGURATION = (
    "YIKE_PILOT_ASSESSMENT_BASE_URL",
    "YIKE_PILOT_ASSESSMENT_API_KEY",
    "YIKE_PILOT_ASSESSMENT_MODEL",
)

_SUGGESTION_CONFIGURATION = (
    "YIKE_PILOT_SEARCH_SUGGESTION_BASE_URL",
    "YIKE_PILOT_SEARCH_SUGGESTION_API_KEY",
    "YIKE_PILOT_SEARCH_SUGGESTION_MODEL",
)


def _suggestion_model(environment: Mapping[str, str]):
    values = tuple(environment.get(name, "") for name in _SUGGESTION_CONFIGURATION)
    present = tuple(bool(value.strip()) for value in values)
    if not any(present):
        return None
    if all(present):
        try:
            return ProcessSearchSuggestionModel(base_url=values[0], api_key=values[1], model=values[2])
        except SearchSuggestionError:
            pass
    raise RuntimeError("invalid_search_suggestion_configuration")


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
    sms_sender=None,
) -> FastAPI:
    environment = os.environ if environment is None else environment
    if environment.get("YIKE_PILOT_ADMIN_DATABASE_URL", "").strip():
        raise RuntimeError("admin_database_url_forbidden_in_web_runtime")
    if any(environment.get(key, '').strip() for key in
           ('YIKE_OPS_DATABASE_URL','YIKE_OPS_PHONE_ENCRYPTION_KEY','YIKE_OPS_PASSWORD')):
        raise RuntimeError('ops_credentials_forbidden_in_web_runtime')

    configured_sender = configured_sms_sender(environment)
    if sms_sender is not None and configured_sender is not None:
        raise RuntimeError('conflicting_sms_configuration')
    if sms_sender is None:
        sms_sender = configured_sender

    model = _assessment_model(environment)
    research_config = research_configuration(environment, model=model, auth_secret=auth_secret)
    store = PilotStore(database)
    # Sender is trusted deployment composition, never an HTTP-supplied URL.
    # A missing provider stays unavailable; a phone secret alone sends no SMS.
    from pilot.trials import TrialPhoneAuthStore
    phone_secret = environment.get('YIKE_PILOT_PHONE_AUTH_SECRET','')
    if sms_sender is not None and not phone_secret:
        raise RuntimeError('phone_auth_configuration_required')
    phone_auth = TrialPhoneAuthStore(database,phone_secret.encode()) if phone_secret else None
    from pilot.access_auth import AccessAuthStore
    access_auth = AccessAuthStore(database,phone_secret.encode()) if phone_secret else None
    strategies = ResearchStrategyStore(database)
    runtime = ExecutionRuntime(database, strategy_resolver=strategies.resolve,
                               capability_check=configured_collection_policy(environment))
    monitor = MonitorRuntime(database, execution_runtime=runtime)
    runtime.monitor_runtime = monitor
    ingestion = CandidateIngestionStore(database, execution_runtime=runtime)
    research_execution = research_quotes = research_runtime = research_resources = None
    if research_config is not None:
        # Do not widen ordinary collection/worker capability when enabling research.
        dynamic_enabled = research_config.dynamic_agent is not None
        research_policy = configured_research_policy(True) if dynamic_enabled else public_research_policy
        research_snapshot = configured_research_snapshot(True) if dynamic_enabled else public_research_snapshot
        research_executor = ExecutionRuntime(database, strategy_resolver=strategies.resolve,
                                             capability_check=research_policy)
        research_quotes = ResearchQuoteService(database, strategies, research_config.rule,
            research_config.signing_secret, research_snapshot)
        research_execution = ResearchExecutionService(research_executor, research_quotes)
        research_resources = ResearchResourceStore(research_executor, rule=research_config.rule,
                                                   research_capability=research_snapshot)
    review = CandidateReviewStore(
        database,
        model=model,
        strategy_resolver=strategies.resolve,
        strategy_snapshot_reader=strategies.read_snapshot,
        research_assessment=ResearchAssessmentRunner(research_resources) if research_resources else None,
    )
    if research_resources is not None:
        research_runtime = ResearchRuntimeService(ResearchOrchestrator(ResearchCandidateStore(research_resources), review))
    replies = ReplyEventStore(database)
    drafts = ContactDraftStore(database)
    outreach_platforms = frozenset(filter(None, (v.strip() for v in
        environment.get('YIKE_PILOT_OUTREACH_PLATFORMS','').split(','))))
    if outreach_platforms - {'BILIBILI','DOUYIN','XIAOHONGSHU','ZHIHU'}:
        raise RuntimeError('invalid_outreach_platform_configuration')
    queue = OutreachQueueStore(database, drafts, runtime, outreach_platforms)
    replies.signed = SignedReplyStore(queue, replies)
    app = build_app(
        store,
        auth_secret=auth_secret,
        dev_login=dev_login,
        phone_auth=phone_auth,
        access_auth=access_auth,
        sms_sender=sms_sender,
        execution_runtime=runtime,
        candidate_ingestion=ingestion,
        candidate_review=review,
        research_strategies=strategies,
        research_quotes=research_quotes,
        research_execution=research_execution,
        research_runtime=research_runtime,
        monitor_plans=MonitorPlanStore(database, strategy_resolver=strategies.resolve),
        monitor_runtime=monitor,
        reply_store=replies,
        contact_drafts=drafts,
        short_coach=ShortCoachService(database, model=ShortCoachModel(model) if model is not None else None),
        structured_followups=FollowupService(database, reply_store=replies),
        opportunity_brief=OpportunityBriefService(database),
        materials=MaterialStore(database, model=MaterialExtractionModel(model) if model is not None else None),
        search_suggestions=SearchSuggestionService(SearchSuggestionStore(database), model=_suggestion_model(environment)),
        outreach_queue=queue,
    )
    if research_runtime is not None and research_config.dynamic_agent is not None:
        journal = ResearchEffectJournal(research_resources)
        dynamic = DynamicResearchRuntimeService(research_runtime, journal=journal,
            candidates=DynamicResearchCandidateStore(journal), agent=research_config.dynamic_agent)
        research_runtime.dynamic = dynamic
        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def dynamic_lifespan(current_app):
            async with original_lifespan(current_app):
                try:
                    yield
                finally:
                    stopped = await run_in_threadpool(dynamic.shutdown, timeout_seconds=5)
                    if not stopped:
                        raise RuntimeError("dynamic_research_shutdown_unconfirmed")

        app.router.lifespan_context = dynamic_lifespan
    return app
