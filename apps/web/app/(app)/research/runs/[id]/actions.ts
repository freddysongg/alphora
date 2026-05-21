"use server";

import { updateTag } from "next/cache";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";

type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];
type PortfolioBriefPublic = components["schemas"]["PortfolioBriefPublic"];
type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];
type CompanyThesisPublic = components["schemas"]["CompanyThesisPublic"];

export interface ActionFailure {
  ok: false;
  error: string;
}

export interface ActionSuccess {
  ok: true;
}

export type ActionResult = ActionSuccess | ActionFailure;

export async function cancelResearchRun(runId: string): Promise<ActionResult> {
  try {
    await getServerApi().POST("/api/research-runs/{run_id}/cancel", {
      params: { path: { run_id: runId } },
    });
  } catch (caught) {
    if (isApiError(caught)) {
      return { ok: false, error: caught.detail };
    }
    return { ok: false, error: "Unable to cancel run." };
  }
  updateTag(`research-run-${runId}`);
  updateTag("research-runs");
  return { ok: true };
}

export async function getMacroBrief(
  runId: string,
): Promise<MacroBriefPublic | null> {
  try {
    const response = await getServerApi().GET(
      "/api/research-runs/{run_id}/macro-brief",
      {
        params: { path: { run_id: runId } },
      },
    );
    if (response.data === undefined) {
      return null;
    }
    return response.data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === 404) {
      return null;
    }
    throw caught;
  }
}

export async function getPortfolioBrief(
  runId: string,
): Promise<PortfolioBriefPublic | null> {
  try {
    const response = await getServerApi().GET(
      "/api/research-runs/{run_id}/portfolio-brief",
      {
        params: { path: { run_id: runId } },
      },
    );
    if (response.data === undefined) {
      return null;
    }
    return response.data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === 404) {
      return null;
    }
    throw caught;
  }
}

export async function getSectorBrief(
  runId: string,
  sectorEntityId: string,
): Promise<SectorBriefPublic | null> {
  try {
    const response = await getServerApi().GET(
      "/api/research-runs/{run_id}/sectors/{sector_entity_id}",
      {
        params: {
          path: { run_id: runId, sector_entity_id: sectorEntityId },
        },
      },
    );
    if (response.data === undefined) {
      return null;
    }
    return response.data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === 404) {
      return null;
    }
    throw caught;
  }
}

export async function getCompanyThesis(
  runId: string,
  companyEntityId: string,
): Promise<CompanyThesisPublic | null> {
  try {
    const response = await getServerApi().GET(
      "/api/research-runs/{run_id}/companies/{company_entity_id}",
      {
        params: {
          path: { run_id: runId, company_entity_id: companyEntityId },
        },
      },
    );
    if (response.data === undefined) {
      return null;
    }
    return response.data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === 404) {
      return null;
    }
    throw caught;
  }
}
