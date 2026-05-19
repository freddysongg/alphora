import type { Metadata } from "next";
import type { ReactElement } from "react";
import { notFound } from "next/navigation";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { getMacroBrief } from "./actions";
import { RunDetail } from "./run-detail";

export const metadata: Metadata = {
  title: "Run Detail · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];

interface RunDetailPageProps {
  params: Promise<{ id: string }>;
}

const NOT_FOUND_STATUS = 404;

async function loadRunDetail(
  runId: string,
): Promise<ResearchRunDetail | null> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs/{run_id}", {
      params: { path: { run_id: runId } },
      cache: "force-cache",
      next: { tags: ["research-runs", `research-run-${runId}`] },
    });
    if (data === undefined) {
      return null;
    }
    return data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadMacroBrief(
  runId: string,
): Promise<MacroBriefPublic | null> {
  try {
    return await getMacroBrief(runId);
  } catch {
    return null;
  }
}

export default async function RunDetailPage(
  props: RunDetailPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  const macroBrief =
    detail.strategy === "funnel_research" ? await loadMacroBrief(id) : null;
  return <RunDetail detail={detail} macroBrief={macroBrief} />;
}
