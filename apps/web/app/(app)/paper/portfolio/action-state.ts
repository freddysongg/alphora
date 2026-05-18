export interface SubmitOrderFieldErrors {
  ticker?: readonly string[];
  quantity?: readonly string[];
  side?: readonly string[];
  order_type?: readonly string[];
  portfolio_id?: readonly string[];
}

export interface SubmitOrderActionState {
  status: "idle" | "ok" | "error";
  message: string | null;
  fields: SubmitOrderFieldErrors;
}

export const initialSubmitOrderState: SubmitOrderActionState = {
  status: "idle",
  message: null,
  fields: {},
};
