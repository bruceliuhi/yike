import { PLATFORMS, type PlatformId } from "./models";

/** Service support is not permission to expand beyond the opportunity's source. */
export function similarResearchDefaultPlatforms(
  source: string,
  supportedPlatforms: readonly PlatformId[],
): PlatformId[] {
  const platform = PLATFORMS.find(
    (p) => p.id === source || p.name === source || p.short === source,
  );
  return platform && supportedPlatforms.includes(platform.id) ? [platform.id] : [];
}
