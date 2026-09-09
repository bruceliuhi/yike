import { newTaskDraft, type TaskDraft } from "../domain/models";
import { makeTerm } from "../domain/task";
import {
  defaultResearchSettings,
  researchSettingsSchema,
} from "../domain/researchUsage";
import type { SimilarResearchHandoff } from "../domain/opportunityResearch";

/** Pure local copy. An estimate from the opportunity drawer is never a start authorization. */
export function createDraftFromResearch(
  input: SimilarResearchHandoff,
): TaskDraft {
  const research = researchSettingsSchema.parse({
    ...defaultResearchSettings(),
    maxSoubei: input.limits.soubei,
    limits: {
      sources: input.limits.sources,
      minutes: input.limits.minutes,
      modelCalls: 50,
    },
    stopAtAnyLimit: input.limits.stopAtAnyLimit,
    provenance: {
      ...input.binding,
      requestId: input.requestId,
      suggestionId: input.suggestionId,
      originalScope: input.originalScope,
      additionalScope: input.additionalScope,
    },
  });
  return {
    ...newTaskDraft(),
    id: input.draftId,
    name: input.name,
    profileId: input.profileId,
    profileVersion: input.profileVersion,
    terms: input.keywords.map((value) => makeTerm(value, "ai")),
    exclusions: input.exclusions.map((value) => makeTerm(value, "ai")),
    platforms: [...input.platforms],
    suggestionProfile: input.profileId,
    research,
  };
}
