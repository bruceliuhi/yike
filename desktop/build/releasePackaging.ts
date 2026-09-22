/** Return whether the current process is creating an installable release. */
export function releasePackagingRequired({
  argv,
  env,
}: {
  argv: readonly string[];
  env: NodeJS.ProcessEnv;
}): boolean {
  if (env.VITEST) return false;
  const lifecycle = env.npm_lifecycle_event ?? "";
  if (/^make(?::|$)/.test(lifecycle)) return true;
  return argv.some((value) => value === "make" || /[\\/]make$/.test(value));
}
