export interface NewRunFieldErrors {
  ticker?: readonly string[];
  trade_date?: readonly string[];
}

export interface NewRunActionState {
  status: "idle" | "error";
  message: string | null;
  fields: NewRunFieldErrors;
}

export const initialNewRunState: NewRunActionState = {
  status: "idle",
  message: null,
  fields: {},
};
