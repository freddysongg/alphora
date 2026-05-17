export const easings = {
  out: [0.23, 1, 0.32, 1],
  inOut: [0.77, 0, 0.175, 1],
  drawer: [0.32, 0.72, 0, 1],
} as const;

export const durations = {
  press: 0.14,
  tooltip: 0.16,
  popover: 0.2,
  sheet: 0.32,
} as const;

export const cssDurations = {
  press: "140ms",
  tooltip: "160ms",
  popover: "200ms",
  sheet: "320ms",
} as const;

export const cssEasings = {
  out: "var(--ease-out)",
  inOut: "var(--ease-in-out)",
  drawer: "var(--ease-drawer)",
} as const;
