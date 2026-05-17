"use client";

import { useState } from "react";
import type { ChangeEvent, ReactElement } from "react";
import { Button, Input } from "@/components/ui";

export interface MaskedKeyInputProps {
  id: string;
  name: string;
  placeholder?: string;
  currentMasked?: string | null;
  hasKey: boolean;
}

const captionClasses = "text-fg-subtle text-xs";

export function MaskedKeyInput(props: MaskedKeyInputProps): ReactElement {
  const { id, name, placeholder, currentMasked, hasKey } = props;
  const [isRevealed, setIsRevealed] = useState(false);
  const [hasLocalValue, setHasLocalValue] = useState(false);

  const resolvedPlaceholder = hasKey
    ? (currentMasked ?? "Key on file")
    : (placeholder ?? "sk-…");
  const caption = hasKey ? "Key on file" : "No key configured";
  const isRevealDisabled = hasKey && !hasLocalValue;

  const handleChange = (event: ChangeEvent<HTMLInputElement>): void => {
    setHasLocalValue(event.target.value.length > 0);
  };

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <Input
          id={id}
          name={name}
          type={isRevealed ? "text" : "password"}
          placeholder={resolvedPlaceholder}
          autoComplete="off"
          spellCheck={false}
          defaultValue=""
          onChange={handleChange}
        />
        <Button
          variant="ghost"
          size="sm"
          type="button"
          onClick={() => setIsRevealed((prev) => !prev)}
          disabled={isRevealDisabled}
          aria-label={isRevealed ? "Hide key" : "Reveal key"}
        >
          {isRevealed ? "Hide" : "Reveal"}
        </Button>
      </div>
      <span className={captionClasses}>{caption}</span>
    </div>
  );
}
