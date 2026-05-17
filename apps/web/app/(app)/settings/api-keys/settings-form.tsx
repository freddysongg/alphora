"use client";

import { useActionState, useCallback, useId, useState } from "react";
import type { ReactElement } from "react";
import { useFormStatus } from "react-dom";
import { toast } from "sonner";

import {
  Button,
  CapsLabel,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";
import type { components } from "@/lib/api";
import {
  initialUpdateSettingsState,
  updateProviderSettings,
} from "./actions";
import type { UpdateSettingsActionState } from "./actions";
import { MaskedKeyInput } from "./masked-key-input";

type LlmProvider = components["schemas"]["LlmProviderEnum"];
type ApplicationSettingsPublic =
  components["schemas"]["ApplicationSettingsPublic"];

interface ProviderOption {
  value: LlmProvider;
  label: string;
}

const providerOptions: readonly ProviderOption[] = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "together", label: "Together" },
];

const sectionClasses =
  "border-t border-line pt-8 mt-8 first:border-0 first:mt-0";
const labelClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

export interface SettingsFormProps {
  initial: ApplicationSettingsPublic;
}

function SubmitButton(): ReactElement {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" disabled={pending}>
      {pending ? "Saving…" : "Save settings"}
    </Button>
  );
}

export function SettingsForm(props: SettingsFormProps): ReactElement {
  const { initial } = props;
  const [provider, setProvider] = useState<LlmProvider>(initial.llm_provider);
  const llmKeyId = useId();
  const alphaVantageKeyId = useId();
  const llmModelId = useId();
  const depthId = useId();
  const defaultModelId = useId();
  const providerErrorId = useId();
  const llmModelErrorId = useId();
  const llmKeyErrorId = useId();
  const alphaVantageKeyErrorId = useId();
  const depthErrorId = useId();
  const defaultModelErrorId = useId();

  const handleSubmit = useCallback(
    async (
      previousState: UpdateSettingsActionState,
      formData: FormData,
    ): Promise<UpdateSettingsActionState> => {
      const next = await updateProviderSettings(previousState, formData);
      if (next.status === "ok") {
        toast.success("Settings saved.");
      } else if (next.status === "error" && next.message !== null) {
        toast.error(next.message);
      }
      return next;
    },
    [],
  );

  const [state, formAction] = useActionState(
    handleSubmit,
    initialUpdateSettingsState,
  );

  return (
    <form action={formAction}>
      <section className={sectionClasses}>
        <CapsLabel as="h2" className="block mb-4">
          LLM PROVIDERS
        </CapsLabel>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <CapsLabel>Default provider</CapsLabel>
            <Select
              name="llm_provider"
              value={provider}
              onValueChange={(next) => setProvider(next as LlmProvider)}
            >
              <SelectTrigger
                aria-invalid={state.fields.llm_provider !== undefined}
                aria-describedby={
                  state.fields.llm_provider !== undefined
                    ? providerErrorId
                    : undefined
                }
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {providerOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {state.fields.llm_provider !== undefined ? (
              <p id={providerErrorId} className="text-xs text-danger">
                {state.fields.llm_provider.join(" ")}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor={llmModelId} className={labelClasses}>
              LLM model
            </label>
            <Input
              id={llmModelId}
              name="llm_model"
              defaultValue={initial.llm_model}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={state.fields.llm_model !== undefined}
              aria-describedby={
                state.fields.llm_model !== undefined
                  ? llmModelErrorId
                  : undefined
              }
            />
            {state.fields.llm_model !== undefined ? (
              <p id={llmModelErrorId} className="text-xs text-danger">
                {state.fields.llm_model.join(" ")}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor={llmKeyId} className={labelClasses}>
              Default LLM API key
            </label>
            <MaskedKeyInput
              id={llmKeyId}
              name="llm_api_key"
              placeholder="sk-…"
              currentMasked={initial.llm_api_key_masked}
              hasKey={initial.has_llm_api_key}
            />
            {state.fields.llm_api_key !== undefined ? (
              <p id={llmKeyErrorId} className="text-xs text-danger">
                {state.fields.llm_api_key.join(" ")}
              </p>
            ) : null}
          </div>
        </div>
      </section>

      <section className={sectionClasses}>
        <CapsLabel as="h2" className="block mb-4">
          MARKET DATA
        </CapsLabel>
        <div className="flex flex-col gap-2">
          <label htmlFor={alphaVantageKeyId} className={labelClasses}>
            Alpha Vantage Key
          </label>
          <MaskedKeyInput
            id={alphaVantageKeyId}
            name="alpha_vantage_key"
            placeholder="AV-…"
            currentMasked={initial.alpha_vantage_key_masked}
            hasKey={initial.has_alpha_vantage_key}
          />
          {state.fields.alpha_vantage_key !== undefined ? (
            <p id={alphaVantageKeyErrorId} className="text-xs text-danger">
              {state.fields.alpha_vantage_key.join(" ")}
            </p>
          ) : null}
        </div>
      </section>

      <section className={sectionClasses}>
        <CapsLabel as="h2" className="block mb-4">
          TRADINGAGENTS
        </CapsLabel>
        <div className="flex flex-col gap-4">
          {/* follow-up: editor for analyst sets */}
          <div className="flex flex-col gap-2">
            <CapsLabel>Default analyst set</CapsLabel>
            {initial.default_analyst_set.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {initial.default_analyst_set.map((analyst) => (
                  <span
                    key={analyst}
                    className="rounded-full border border-line bg-surface-2 px-3 py-1 text-xs text-fg-muted"
                  >
                    {analyst}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-xs text-fg-subtle">No analysts configured.</span>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor={depthId} className={labelClasses}>
              Default depth
            </label>
            <Input
              id={depthId}
              name="default_depth"
              type="number"
              defaultValue={initial.default_depth}
              min={1}
              max={10}
              step={1}
              aria-invalid={state.fields.default_depth !== undefined}
              aria-describedby={
                state.fields.default_depth !== undefined
                  ? depthErrorId
                  : undefined
              }
            />
            {state.fields.default_depth !== undefined ? (
              <p id={depthErrorId} className="text-xs text-danger">
                {state.fields.default_depth.join(" ")}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor={defaultModelId} className={labelClasses}>
              Default model
            </label>
            <Input
              id={defaultModelId}
              name="default_model"
              defaultValue={initial.default_model}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={state.fields.default_model !== undefined}
              aria-describedby={
                state.fields.default_model !== undefined
                  ? defaultModelErrorId
                  : undefined
              }
            />
            {state.fields.default_model !== undefined ? (
              <p id={defaultModelErrorId} className="text-xs text-danger">
                {state.fields.default_model.join(" ")}
              </p>
            ) : null}
          </div>
        </div>
      </section>

      <div className="mt-8 flex justify-end">
        <SubmitButton />
      </div>
    </form>
  );
}
