"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import { Button, Input } from "@/components/ui";

export interface MaskedKeyInputProps {
  id: string;
  placeholder?: string;
}

export function MaskedKeyInput(props: MaskedKeyInputProps): ReactElement {
  const { id, placeholder } = props;
  const [isRevealed, setIsRevealed] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <Input
        id={id}
        type={isRevealed ? "text" : "password"}
        placeholder={placeholder ?? "sk-…"}
        autoComplete="off"
        spellCheck={false}
      />
      <Button
        variant="ghost"
        size="sm"
        type="button"
        onClick={() => setIsRevealed((prev) => !prev)}
        aria-label={isRevealed ? "Hide key" : "Reveal key"}
      >
        {isRevealed ? "Hide" : "Reveal"}
      </Button>
    </div>
  );
}
