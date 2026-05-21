"use client";

import type { ReactElement } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CapsLabel,
  HexPill,
} from "@/components/ui";
import type { components } from "@/lib/api";

type HypothesisPublic = components["schemas"]["HypothesisPublic"];
type HypothesisLifecycleResponse =
  components["schemas"]["HypothesisLifecycleResponse"];

export interface HypothesisLifecycleBundle {
  hypothesis: HypothesisPublic;
  lifecycle: HypothesisLifecycleResponse | null;
}

export interface HypothesisLifecycleCardProps {
  bundles: readonly HypothesisLifecycleBundle[];
}

const TERMINAL_STATES = new Set([
  "validated",
  "falsified",
  "expired",
  "superseded",
]);

function stateTone(state: string): string {
  if (state === "validated") {
    return "text-accent-text";
  }
  if (state === "falsified") {
    return "text-danger";
  }
  if (state === "expired" || state === "superseded") {
    return "text-fg-subtle";
  }
  if (state === "active") {
    return "text-accent";
  }
  return "text-fg-subtle";
}

function formatTimestamp(value: string | null): string {
  if (value === null) {
    return "—";
  }
  return new Date(value).toISOString();
}

export function HypothesisLifecycleCard(
  props: HypothesisLifecycleCardProps,
): ReactElement {
  const { bundles } = props;
  if (bundles.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>HYPOTHESIS LIFECYCLE</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No hypotheses with lifecycle state to display.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>HYPOTHESIS LIFECYCLE</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-6">
          {bundles.map((bundle) => (
            <LifecycleRow key={bundle.hypothesis.id} bundle={bundle} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function LifecycleRow(props: {
  bundle: HypothesisLifecycleBundle;
}): ReactElement {
  const { bundle } = props;
  const hypothesis = bundle.hypothesis;
  const lifecycle = bundle.lifecycle;
  const isTerminal = TERMINAL_STATES.has(hypothesis.state);
  const stagnationFlagged = hypothesis.stagnation_flagged_at !== null;
  const children = lifecycle?.children ?? [];
  const conditionalEdges = lifecycle?.conditional_edges ?? [];
  const recentResolutions = lifecycle?.recent_event_resolutions ?? [];
  const supersededBy = lifecycle?.superseded_by ?? null;
  const supersedes = lifecycle?.supersedes ?? null;
  const parent = lifecycle?.parent ?? null;

  return (
    <li className="flex flex-col gap-3 border-t border-line/60 pt-4 first:border-t-0 first:pt-0">
      <header className="flex items-center gap-3">
        <CapsLabel className={`w-24 shrink-0 ${stateTone(hypothesis.state)}`}>
          {hypothesis.state}
        </CapsLabel>
        <p className="flex-1 min-w-0 text-sm text-fg">
          {hypothesis.claim_text}
        </p>
        <HexPill value={hypothesis.id} />
      </header>

      <dl className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
        <LifecycleField
          label="LAST ACTIVITY"
          value={formatTimestamp(hypothesis.last_activity_at)}
        />
        <LifecycleField
          label="VALID UNTIL"
          value={formatTimestamp(hypothesis.valid_until)}
        />
        <LifecycleField
          label="STAGNATION"
          value={
            stagnationFlagged
              ? formatTimestamp(hypothesis.stagnation_flagged_at)
              : "—"
          }
          tone={stagnationFlagged ? "text-danger" : "text-fg-subtle"}
        />
        <LifecycleField
          label="ARCHIVED"
          value={
            isTerminal
              ? `${formatTimestamp(hypothesis.archived_at)} (${hypothesis.archived_reason ?? "—"})`
              : "—"
          }
          tone={isTerminal ? "text-fg-muted" : "text-fg-subtle"}
        />
      </dl>

      {parent !== null ? (
        <RelationshipRow label="PARENT" hypothesis={parent} />
      ) : null}
      {supersedes !== null ? (
        <RelationshipRow label="SUPERSEDES" hypothesis={supersedes} />
      ) : null}
      {supersededBy !== null ? (
        <RelationshipRow label="SUPERSEDED BY" hypothesis={supersededBy} />
      ) : null}
      {children.length > 0 ? <ChildrenRow items={children} /> : null}
      {conditionalEdges.length > 0 ? (
        <ConditionalEdgesTable edges={conditionalEdges} />
      ) : null}
      {recentResolutions.length > 0 ? (
        <RecentResolutionsTable resolutions={recentResolutions} />
      ) : null}
    </li>
  );
}

function LifecycleField(props: {
  label: string;
  value: string;
  tone?: string;
}): ReactElement {
  const tone = props.tone ?? "text-fg";
  return (
    <div className="flex flex-col gap-1">
      <CapsLabel className="text-fg-subtle">{props.label}</CapsLabel>
      <span className={`font-mono tabular-nums ${tone}`}>{props.value}</span>
    </div>
  );
}

function RelationshipRow(props: {
  label: string;
  hypothesis: HypothesisPublic;
}): ReactElement {
  return (
    <div className="flex items-center gap-3 text-xs text-fg-muted">
      <CapsLabel className="text-fg-subtle w-28 shrink-0">
        {props.label}
      </CapsLabel>
      <span className="flex-1 min-w-0 truncate">
        {props.hypothesis.claim_text}
      </span>
      <HexPill value={props.hypothesis.id} />
    </div>
  );
}

function ChildrenRow(props: {
  items: readonly HypothesisPublic[];
}): ReactElement {
  return (
    <div className="flex flex-col gap-1 text-xs text-fg-muted">
      <CapsLabel className="text-fg-subtle">CHILDREN</CapsLabel>
      <ul className="flex flex-col gap-1">
        {props.items.map((child) => (
          <li
            key={child.id}
            className="flex items-center gap-3"
          >
            <span className="flex-1 min-w-0 truncate">{child.claim_text}</span>
            <HexPill value={child.id} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ConditionalEdgesTable(props: {
  edges: readonly components["schemas"]["ConditionalEdgePublic"][];
}): ReactElement {
  return (
    <div className="flex flex-col gap-1 text-xs">
      <CapsLabel className="text-fg-subtle">CONDITIONAL EDGES</CapsLabel>
      <table className="w-full font-mono tabular-nums">
        <thead className="text-fg-subtle border-b border-line/60">
          <tr>
            <th className="text-left py-1 pr-3">type</th>
            <th className="text-left py-1 pr-3">event</th>
            <th className="text-left py-1">id</th>
          </tr>
        </thead>
        <tbody>
          {props.edges.map((edge) => (
            <tr key={edge.relation_id} className="border-b border-line/40">
              <td className="text-left py-1 pr-3 text-fg-muted">
                {edge.relation_type}
              </td>
              <td className="text-left py-1 pr-3 text-fg">
                {edge.event_entity_name ?? "—"}
              </td>
              <td className="text-left py-1">
                <HexPill value={edge.event_entity_id} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecentResolutionsTable(props: {
  resolutions: readonly components["schemas"]["EventResolutionPublic"][];
}): ReactElement {
  return (
    <div className="flex flex-col gap-1 text-xs">
      <CapsLabel className="text-fg-subtle">RECENT EVENT RESOLUTIONS</CapsLabel>
      <table className="w-full font-mono tabular-nums">
        <thead className="text-fg-subtle border-b border-line/60">
          <tr>
            <th className="text-left py-1 pr-3">resolved at</th>
            <th className="text-left py-1 pr-3">kind</th>
            <th className="text-left py-1">notes</th>
          </tr>
        </thead>
        <tbody>
          {props.resolutions.map((resolution) => (
            <tr
              key={resolution.id}
              className="border-b border-line/40"
            >
              <td className="text-left py-1 pr-3 text-fg-muted">
                {formatTimestamp(resolution.resolved_at)}
              </td>
              <td className="text-left py-1 pr-3 text-fg">{resolution.kind}</td>
              <td className="text-left py-1 text-fg-subtle truncate">
                {resolution.notes ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
