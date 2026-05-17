import type { ReactElement, ReactNode } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { CommandPaletteMount } from "@/components/shell/command-palette-mount";

interface AppGroupLayoutProps {
  children: ReactNode;
}

export default function AppGroupLayout(props: AppGroupLayoutProps): ReactElement {
  const { children } = props;
  return (
    <AppShell>
      {children}
      <CommandPaletteMount />
    </AppShell>
  );
}
