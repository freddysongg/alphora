import type { Metadata } from "next";
import type { ReactElement } from "react";
import {
  CapsLabel,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";

export const metadata: Metadata = {
  title: "Account Settings · Alphora",
};

const sectionClasses = "border-t border-line pt-8 mt-8 first:border-0 first:mt-0";
const labelClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

export default function AccountSettingsPage(): ReactElement {
  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <header className="pb-2">
        <CapsLabel as="h1">SETTINGS · ACCOUNT</CapsLabel>
      </header>

      <section className={sectionClasses}>
        <CapsLabel as="h2" className="block mb-4">
          ACCOUNT
        </CapsLabel>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label htmlFor="account-email" className={labelClasses}>
              Email
            </label>
            <Input
              id="account-email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="account-name" className={labelClasses}>
              Display name
            </label>
            <Input
              id="account-name"
              placeholder="Freddy Song"
              autoComplete="name"
            />
          </div>
        </div>
      </section>

      <section className={sectionClasses}>
        <CapsLabel as="h2" className="block mb-4">
          PROFILE
        </CapsLabel>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label htmlFor="account-tz" className={labelClasses}>
              Default timezone
            </label>
            <Input
              id="account-tz"
              placeholder="America/New_York"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-2">
            <CapsLabel>Theme</CapsLabel>
            <Select defaultValue="dark">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="dark">Dark</SelectItem>
                <SelectItem value="light" disabled>
                  Light (coming soon)
                </SelectItem>
              </SelectContent>
            </Select>
            <span className="text-xs text-fg-subtle">
              Light theme is not yet available.
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
