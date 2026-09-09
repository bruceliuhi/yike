const referenceRoutes: Record<string, string> = {
  P07: "/candidates?scope=sample",
  P10: "/opportunities?scope=sample",
  P11: "/opportunities/sample",
  P12: "/outreach?opportunity=sample&channel=comment",
  P13: "/outreach?opportunity=sample&channel=comment&confirm=send",
};

/** R3 sample pages stay read-only; failure/recovery cases use TEST customers. */
export function referenceRoute(
  page: string,
  reference: boolean,
  state: string,
  recovery?: string,
): string | undefined {
  if (!reference || state === "error" || state === "loading" || recovery)
    return;
  return referenceRoutes[page];
}
