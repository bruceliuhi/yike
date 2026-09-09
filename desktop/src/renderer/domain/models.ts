export type PageId = `P${string}`;
export type PlatformId = "xhs" | "douyin" | "bilibili" | "zhihu" | "web";
export type LoadState = "idle" | "loading" | "success" | "error";
export interface ProfileFields {
  service: string;
  customer: string;
  regions: string;
  preference: string;
  exclusions: string;
}
export interface Profile {
  /** Version-row ID. Never substitute the stable profile entity ID here. */
  id: string;
  /** Stable entity ID supplied by the service; absent for legacy responses. */
  profileEntityId?: string;
  version: number;
  status: "DRAFT" | "CONFIRMED" | "REVOKED";
  fields: ProfileFields;
  description: string;
}
export interface Term {
  id: string;
  value: string;
  origin: "ai" | "manual";
  edited: boolean;
}
export interface Schedule {
  policyVersion?: 1;
  kind: "daily" | "interval";
  times: string[];
  interval: number;
  start: string;
  end: string;
  timezone: string;
}
export interface TaskDraft {
  research?: import("./researchUsage").ResearchSettings;
  templateSourceDraftIds?: string[];
  id: string;
  revision: number;
  name: string;
  profileId: string;
  profileVersion: number | null;
  terms: Term[];
  exclusions: Term[];
  removed: string[];
  source: "search" | "links";
  links: string;
  platforms: PlatformId[];
  accounts: Partial<Record<PlatformId, string>>;
  mode: "once" | "monitor";
  schedule: Schedule;
  savedAt: string | null;
  suggestionProfile: string | null;
}
export interface PlatformConnection {
  platform: PlatformId;
  status: "CONNECTED" | "DISCONNECTED" | "EXPIRED" | "LIMITED" | "UNAVAILABLE" | "UNVERIFIED";
  accountId?: string;
  accountName?: string;
  capabilities: string[];
  reason?: string;
  /** Server registration identity. It is not an execution capability or a session credential. */
  registration?: {
    connectionId: string;
    deviceId: string;
    version: number;
    connectedAt: string;
    disconnectedAt: string | null;
  };
}
export interface Suggestion {
  keywords: string[];
  exclusions: string[];
  profileId: string;
  requestId: string;
}
export interface Opportunity {
  sourceObservedAt?: string;
  sourceEvidenceVersion?: string;
  libraryFacts?: import("./opportunityLibrary").OpportunityLibraryFacts | null;
  id: string;
  title: string;
  buyer: string;
  summary: string;
  excerpt: string;
  matchReason: string;
  actionSignal: string;
  value: string;
  risk: string;
  contactPath: string;
  url: string;
  platform: string;
  sourceStatus: string;
  profileStatus: string;
  profileVersionId: string;
  reviewer: string;
  reviewedAt: string;
  publishedAt: string;
  updatedAt: string;
  intentStatus: string;
  comment: string;
  dm: string;
  sample?: boolean;
}
export type FollowupStatus =
  "CONTACTED" | "REPLIED" | "MEETING" | "QUOTED" | "LOST" | "WON";
export interface Followup {
  id: string;
  opportunityId: string;
  title: string;
  status: FollowupStatus;
  note: string;
  createdAt: string;
  kind: "manual" | "platform";
}
export interface MaterialDraft {
  id: string;
  name: string;
  text: string;
  visibility: "internal" | "external";
  fileName?: string;
  bytes?: number;
  updatedAt: string;
}
export interface ContactDraft {
  opportunityId: string;
  channel: "comment" | "dm";
  content: string;
  version: number;
  savedContent: string;
  accountId: string;
  recipient: string;
  confirmedFingerprint?: string;
}
export interface ContactVerification {
  allowed: boolean;
  fingerprint: string;
  confirmationToken: string;
  expiresAt: string;
  opportunityId: string;
  accountId: string;
  channel: "comment" | "dm";
  recipientId: string;
  recipientLabel: string;
  reason?: string;
}
export interface RuntimeInfo {
  version: string;
  platform: string;
  serviceConfigured: boolean;
  deviceReady?: boolean;
}
export interface Session {
  authenticated: boolean;
  userId?: string;
  /** Supplied by the authenticated service, never inferred from resource data. */
  accountScope?: { id: string; version: number };
}
export type TaskAction = "pause" | "resume" | "cancel" | "retry";
export interface TaskPlatformStage {
  platform: PlatformId;
  status: string;
  phase?: string;
  reason?: string;
  accountName?: string;
  newCount?: number;
  updatedAt?: string;
  nextRetryAt?: string;
}
export interface TaskRunEvent {
  id: string;
  message: string;
  occurredAt?: string;
  platform?: PlatformId;
  level?: "info" | "warning" | "error";
}
export interface TaskRun {
  id: string;
  name: string;
  mode: "once" | "monitor";
  status: string;
  platforms: PlatformId[];
  updatedAt?: string;
  profileId?: string;
  profileVersion?: number;
  profileName?: string;
  keywords?: string[];
  regions?: string;
  createdAt?: string;
  schedule?: Schedule;
  lastRunAt?: string;
  nextRunAt?: string;
  failureReason?: string;
  platformStages?: TaskPlatformStage[];
  events?: TaskRunEvent[];
  statistics?: {
    today?: number;
    week?: number;
    month?: number;
    total?: number;
  };
}
export const PLATFORMS: { id: PlatformId; name: string; short: string }[] = [
  { id: "xhs", name: "小红书", short: "小红书" },
  { id: "douyin", name: "抖音", short: "抖音" },
  { id: "bilibili", name: "B站", short: "B站" },
  { id: "zhihu", name: "知乎", short: "知乎" },
  { id: "web", name: "公开网站", short: "公开网站" },
];
export const EMPTY_PROFILE: ProfileFields = {
  service: "",
  customer: "",
  regions: "",
  preference: "",
  exclusions: "",
};
export function newTaskDraft(mode: "once" | "monitor" = "once"): TaskDraft {
  return {
    id: crypto.randomUUID(),
    revision: 1,
    name: "",
    profileId: "",
    profileVersion: null,
    terms: [],
    exclusions: [],
    removed: [],
    source: "search",
    links: "",
    platforms: [],
    accounts: {},
    mode,
    schedule: {
      policyVersion: 1,
      kind: "daily",
      times: ["09:00"],
      interval: 3,
      start: "09:00",
      end: "18:00",
      timezone:
        Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai",
    },
    savedAt: null,
    suggestionProfile: null,
  };
}
