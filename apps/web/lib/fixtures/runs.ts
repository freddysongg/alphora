export type RunStatus = "queued" | "running" | "succeeded" | "failed";
export type RunRating = "buy" | "hold" | "sell" | "none";

export interface ResearchRun {
  id: string;
  ticker: string;
  status: RunStatus;
  rating: RunRating;
  activity: readonly number[];
  startedAt: string;
  durationMs: number | null;
}

const activityA: readonly number[] = [
  2, 4, 1, 6, 3, 8, 12, 9, 5, 7, 11, 14, 10, 6, 4, 8, 13, 9, 5, 3, 7, 6, 2, 4,
];
const activityB: readonly number[] = [
  1, 0, 0, 2, 3, 5, 8, 11, 14, 18, 22, 19, 17, 12, 9, 7, 5, 3, 2, 4, 6, 8, 5, 2,
];
const activityC: readonly number[] = [
  6, 8, 10, 12, 14, 16, 18, 22, 20, 18, 16, 14, 12, 10, 8, 6, 4, 2, 1, 0, 0, 1, 3, 5,
];
const activityD: readonly number[] = [
  0, 0, 0, 0, 1, 2, 4, 7, 10, 14, 19, 24, 28, 25, 21, 18, 15, 12, 9, 6, 4, 2, 1, 0,
];

export const sampleRuns: readonly ResearchRun[] = [
  {
    id: "sb-aLPQ00ucncCYFzzZ0qiNoL",
    ticker: "AAPL",
    status: "queued",
    rating: "none",
    activity: activityB,
    startedAt: "2026-05-16T14:32:00Z",
    durationMs: null,
  },
  {
    id: "sb-bQRpX1vdndDZGazz1rjOpM",
    ticker: "NVDA",
    status: "queued",
    rating: "none",
    activity: activityA,
    startedAt: "2026-05-16T14:30:00Z",
    durationMs: null,
  },
  {
    id: "sb-cSTpY2weoeEAHbaa2skPqN",
    ticker: "TSLA",
    status: "running",
    rating: "none",
    activity: activityC,
    startedAt: "2026-05-16T14:24:00Z",
    durationMs: null,
  },
  {
    id: "sb-dUVqZ3xfpfFBIcbb3tlQrO",
    ticker: "META",
    status: "running",
    rating: "none",
    activity: activityD,
    startedAt: "2026-05-16T14:18:00Z",
    durationMs: null,
  },
  {
    id: "sb-eWXr04ygqgGCJdcc4umRsP",
    ticker: "GOOGL",
    status: "succeeded",
    rating: "buy",
    activity: activityA,
    startedAt: "2026-05-16T13:54:00Z",
    durationMs: 758000,
  },
  {
    id: "sb-fXYs15zhrhHDKedd5vnStQ",
    ticker: "MSFT",
    status: "succeeded",
    rating: "buy",
    activity: activityB,
    startedAt: "2026-05-16T13:41:00Z",
    durationMs: 612000,
  },
  {
    id: "sb-gYZt26aisiIELfee6woTuR",
    ticker: "AMZN",
    status: "succeeded",
    rating: "hold",
    activity: activityC,
    startedAt: "2026-05-16T13:18:00Z",
    durationMs: 891000,
  },
  {
    id: "sb-hZAu37bjtjJFMgff7xpUvS",
    ticker: "AMD",
    status: "succeeded",
    rating: "buy",
    activity: activityD,
    startedAt: "2026-05-16T12:55:00Z",
    durationMs: 734000,
  },
  {
    id: "sb-iABv48ckukKGNhgg8yqVwT",
    ticker: "NFLX",
    status: "succeeded",
    rating: "sell",
    activity: activityA,
    startedAt: "2026-05-16T12:32:00Z",
    durationMs: 522000,
  },
  {
    id: "sb-jBCw59dlvlLHOihh9zrWxU",
    ticker: "CRM",
    status: "succeeded",
    rating: "hold",
    activity: activityB,
    startedAt: "2026-05-16T12:11:00Z",
    durationMs: 645000,
  },
  {
    id: "sb-kCDx60emwmMIPjii0asXyV",
    ticker: "ORCL",
    status: "failed",
    rating: "none",
    activity: activityC,
    startedAt: "2026-05-16T11:48:00Z",
    durationMs: 142000,
  },
  {
    id: "sb-lDEy71fnxnNJQkjj1btYzW",
    ticker: "INTC",
    status: "failed",
    rating: "none",
    activity: activityD,
    startedAt: "2026-05-16T11:22:00Z",
    durationMs: 89000,
  },
] as const;
