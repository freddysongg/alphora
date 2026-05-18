const FALLBACK = "—";

function pad(value: number, width: number): string {
  return value.toString().padStart(width, "0");
}

export function formatDateTime(iso: string): string {
  if (typeof iso !== "string" || iso.length === 0) {
    return FALLBACK;
  }
  const parsed = new Date(iso);
  const epoch = parsed.getTime();
  if (Number.isNaN(epoch)) {
    return FALLBACK;
  }
  const year = pad(parsed.getUTCFullYear(), 4);
  const month = pad(parsed.getUTCMonth() + 1, 2);
  const day = pad(parsed.getUTCDate(), 2);
  const hours = pad(parsed.getUTCHours(), 2);
  const minutes = pad(parsed.getUTCMinutes(), 2);
  const seconds = pad(parsed.getUTCSeconds(), 2);
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}
