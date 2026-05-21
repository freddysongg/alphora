import { redirect } from "next/navigation";
import type { Route } from "next";
import type { ReactElement } from "react";

interface RedirectPageProps {
  params: Promise<{ id: string }>;
}

export default async function ObservabilityIndexRedirect(
  props: RedirectPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  redirect(`/research/runs/${id}#observability` as Route);
}
