const FALLBACK = "—";
const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;

function pad2(value: number): string {
  return value.toString().padStart(2, "0");
}

export function formatWallClock(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) {
    return FALLBACK;
  }
  if (!Number.isFinite(ms) || ms < 0) {
    return FALLBACK;
  }
  const totalSeconds = Math.floor(ms / MS_PER_SECOND);
  if (totalSeconds < SECONDS_PER_MINUTE) {
    return `${totalSeconds}s`;
  }
  const totalMinutes = Math.floor(totalSeconds / SECONDS_PER_MINUTE);
  const seconds = totalSeconds % SECONDS_PER_MINUTE;
  if (totalMinutes < MINUTES_PER_HOUR) {
    return `${totalMinutes}m ${seconds}s`;
  }
  const hours = Math.floor(totalMinutes / MINUTES_PER_HOUR);
  const minutes = totalMinutes % MINUTES_PER_HOUR;
  return `${hours}h ${pad2(minutes)}m`;
}
