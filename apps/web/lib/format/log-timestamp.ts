const FALLBACK_TIMESTAMP = "--:--:--.---";

function pad(value: number, width: number): string {
  return value.toString().padStart(width, "0");
}

export function formatLogTimestamp(iso: string): string {
  if (typeof iso !== "string" || iso.length === 0) {
    return FALLBACK_TIMESTAMP;
  }
  const parsed = new Date(iso);
  const epoch = parsed.getTime();
  if (Number.isNaN(epoch)) {
    return FALLBACK_TIMESTAMP;
  }
  const hours = pad(parsed.getUTCHours(), 2);
  const minutes = pad(parsed.getUTCMinutes(), 2);
  const seconds = pad(parsed.getUTCSeconds(), 2);
  const millis = pad(parsed.getUTCMilliseconds(), 3);
  return `${hours}:${minutes}:${seconds}.${millis}`;
}
