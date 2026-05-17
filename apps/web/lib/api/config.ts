export type ConfigRecord = Record<string, unknown>;

export function readNumber(
  config: ConfigRecord | null | undefined,
  key: string,
): number | null {
  if (config === null || config === undefined) {
    return null;
  }
  const raw = config[key];
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return raw;
  }
  return null;
}

export function readStringArray(
  config: ConfigRecord | null | undefined,
  key: string,
): readonly string[] {
  if (config === null || config === undefined) {
    return [];
  }
  const raw = config[key];
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: string[] = [];
  for (const entry of raw) {
    if (typeof entry === "string") {
      out.push(entry);
    }
  }
  return out;
}
