import type {
  CoverageSnapshot,
  SearchCoverageQuery,
} from "../domain/searchCoverage";

/** Optional, read-only, authenticated coverage API. No fallback to TaskRun.events.
 * The adapter must verify session accountScope before exposing this capability.
 * query.expectedScope is checked against server authentication, never used to select
 * an arbitrary account. Returns one bounded, internally consistent run/window snapshot.
 * It performs no new collection, quota reservation, resumption or charge. */
export interface SearchCoverageService {
  query(
    request: SearchCoverageQuery,
    signal?: AbortSignal,
  ): Promise<CoverageSnapshot>;
}
