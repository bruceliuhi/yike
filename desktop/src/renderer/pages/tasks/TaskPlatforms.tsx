import { PlatformLabel } from "../../components/Platform";
export function TaskPlatforms({
  platforms,
  size = 16,
  empty = "尚未选择平台",
}: {
  platforms: string[];
  size?: number;
  empty?: string;
}) {
  return platforms.length ? (
    <span className="task-platforms">
      {platforms.map((platform) => (
        <PlatformLabel key={platform} platform={platform} size={size} />
      ))}
    </span>
  ) : (
    <>{empty}</>
  );
}
