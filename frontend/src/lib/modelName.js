// Convert API model id ("claude-opus-4-7" / "claude-sonnet-4-5-20250929") into a
// human label ("Claude Opus 4.7", "Claude Sonnet 4.5").
// Returns null when no model id is present (AI path failed / has not run) so
// callers do not fabricate a specific model that never produced output.
export function formatModelName(modelId) {
  if (!modelId || typeof modelId !== "string") return null;
  // Strip date suffix like "-20260416" (any 8-digit tail)
  const m = modelId.replace(/-\d{8}$/, "");
  // claude-opus-4-7 -> ["claude","opus","4","7"]
  const parts = m.split("-");
  if (parts.length < 3) return modelId;
  const vendor = parts[0]; // "claude"
  const family = parts[1]; // "opus" | "sonnet" | "haiku"
  // Remaining parts are version digits
  const ver = parts.slice(2).join(".");
  const vendorLabel = vendor.charAt(0).toUpperCase() + vendor.slice(1);
  const familyLabel = family.charAt(0).toUpperCase() + family.slice(1);
  return `${vendorLabel} ${familyLabel} ${ver}`;
}
