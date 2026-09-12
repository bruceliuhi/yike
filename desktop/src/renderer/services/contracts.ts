import type {
  Session,
  Profile,
  ProfileFields,
  Opportunity,
  Followup,
  FollowupStatus,
  PlatformConnection,
  Suggestion,
  TaskDraft,
  TaskRun,
  ContactDraft,
  RuntimeInfo,
} from "../domain/models";
import type {
  CandidatePage,
  CandidateQuery,
  CandidateReview,
  CandidateReviewResult,
} from "../domain/candidates";
export class ServiceError extends Error {
  constructor(
    public code: string,
    message: string,
    public status = 0,
  ) {
    super(message);
    this.name = "ServiceError";
  }
}
export function errorMessage(error: unknown): string {
  return error instanceof ServiceError
    ? error.message
    : error instanceof Error
      ? error.message
      : "操作未完成，请重试。";
}
export interface YikeService {
  searchSuggestions?: import('./searchSuggestions').SearchSuggestionsService;
  taskFeed?: import('./taskFeed').TaskFeedService;
  monitorCollection?: import('./monitorCollection').MonitorCollectionService;
  execution?: import('./desktopExecution').DesktopExecutionService;
  foregroundCollection?: import('./foregroundCollection').ForegroundCollectionService;
  deviceIdentity?: import('./deviceIdentity').DeviceIdentityApi;
  candidateReview?: import("./candidateReview").CandidateReviewService;
  rawCandidateEvidence?: import("./candidateReview").CandidateReviewService["getRawEvidence"];
  researchStrategies?: import("./researchStrategies").ResearchStrategiesService;
  coveragePlans?: import("./coveragePlan").CoveragePlanService;
  opportunityBrief?: import("./opportunityBrief").OpportunityBriefService;
  researchUsage?: import("./researchUsage").ResearchUsageService;
  researchRuntime?: import('./researchRuntime').ResearchRuntimeService;
  shortCoach?: import("./shortCoach").ShortCoachService;
  contactDrafts?: import("./shortCoach").ContactDraftService;
  opportunityResearch?: import("./opportunityResearch").OpportunityResearchService;
  searchCoverage?: import("./searchCoverage").SearchCoverageService;
  materials?: import("./materials").MaterialService;
  followup?: import("./followup").FollowupService;
  replyEvidence?(opportunityId:string,signal?:AbortSignal):Promise<unknown>;
  taskOperations?: import("./taskOperations").TaskOperationsService;
  workbench?: import("./workbench").WorkbenchService;
  outreach?: import("./outreach").OutreachService;
  management?: import("./management").ManagementService;
  verifyContact(
    draft: ContactDraft,
    fingerprint: string,
  ): Promise<import("../domain/models").ContactVerification>;
  candidates(
    query?: CandidateQuery,
    signal?: AbortSignal,
  ): Promise<CandidatePage>;
  reviewCandidate(review: CandidateReview): Promise<CandidateReviewResult>;
  session(): Promise<Session>;
  loginToken(token: string): Promise<Session>;
  loginAccess?(code: string): Promise<Session>;
  logout(): Promise<void>;
  requestCode(phone: string): Promise<{ retryAfter: number }>;
  login(phone: string, code: string, trial?: string): Promise<Session>;
  profiles(): Promise<Profile[]>;
  saveProfile(fields: ProfileFields, references?: import('../../shared/profileMaterialReferences').ProfileReferenceOptions): Promise<Profile>;
  confirmProfile(id: string): Promise<Profile>;
  opportunities(): Promise<Opportunity[]>;
  opportunity(id: string, signal?: AbortSignal): Promise<Opportunity>;
  followups(): Promise<Followup[]>;
  addFollowup(id: string, status: FollowupStatus, note: string): Promise<void>;
  connections(): Promise<PlatformConnection[]>;
  connect(platform: string, signal?: AbortSignal): Promise<void>;
  cancelConnection?(platform: string): Promise<void>;
  connectionLoginStatus?(platform: string): Promise<'WAITING_LOGIN'|'LOGIN_READY'>;
  checkConnection(platform: string): Promise<PlatformConnection>;
  disconnect(platform: string): Promise<void>;
  suggest(
    profileId: string,
    requestId: string,
    signal?: AbortSignal,
  ): Promise<Suggestion>;
  tasks(): Promise<TaskRun[]>;
  startTask(draft: TaskDraft, requestId: string): Promise<TaskRun>;
  taskAction(
    id: string,
    action: "pause" | "resume" | "cancel" | "retry",
  ): Promise<void>;
  generateContact(id: string, channel: "comment" | "dm"): Promise<string>;
  saveContact(draft: ContactDraft): Promise<void>;
  send(draft: ContactDraft, confirmation: string): Promise<{ status: string }>;
  activate(code: string): Promise<void>;
  checkUpdate(): Promise<{ available: boolean; version?: string }>;
  info(): Promise<RuntimeInfo>;
  openExternal(url: string): Promise<void>;
  copy(text: string): Promise<void>;
}
