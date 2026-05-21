export interface UpdateSettingsFieldErrors {
  llm_provider?: readonly string[];
  llm_model?: readonly string[];
  llm_api_key?: readonly string[];
  alpha_vantage_key?: readonly string[];
  default_depth?: readonly string[];
  default_model?: readonly string[];
}

export interface UpdateSettingsActionState {
  status: "idle" | "ok" | "error";
  message: string | null;
  fields: UpdateSettingsFieldErrors;
}

export const initialUpdateSettingsState: UpdateSettingsActionState = {
  status: "idle",
  message: null,
  fields: {},
};
