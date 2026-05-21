export interface RunScreenerActionState {
  status: "idle" | "error";
  message: string | null;
  fields: Readonly<Record<string, readonly string[]>>;
}

export const initialRunScreenerState: RunScreenerActionState = {
  status: "idle",
  message: null,
  fields: {},
};
