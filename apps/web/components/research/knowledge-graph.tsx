"use client";

import type { ReactElement } from "react";
import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import type { components } from "@/lib/api";
import { colorTokens } from "@/lib/tokens";

type RunGraph = components["schemas"]["RunGraph"];
type GraphNode = components["schemas"]["GraphNode"];
type GraphEdge = components["schemas"]["GraphEdge"];
type EntityType = components["schemas"]["EntityTypeEnum"];
type HypothesisStatus = components["schemas"]["HypothesisStatusEnum"];

export interface KnowledgeGraphProps {
  graph: RunGraph | null;
}

interface NodeRenderData extends Record<string, unknown> {
  label: string;
  type: EntityType;
  isHypothesis: boolean;
  hypothesisStatus: HypothesisStatus | null;
  belief: number | null;
}

const ENTITY_TYPE_COLORS: Record<EntityType, string> = {
  company: colorTokens.accent,
  person: colorTokens.accentSoft,
  sector: colorTokens.accentDeep,
  country: colorTokens.fgMuted,
  product: colorTokens.fg,
  regulator: colorTokens.warn,
  bill: colorTokens.warn,
  event: colorTokens.success,
  document: colorTokens.fgMuted,
  instrument: colorTokens.accent,
  theme: colorTokens.accentSoft,
  hypothesis: colorTokens.accentPress,
};

const HYPOTHESIS_BORDER: Record<HypothesisStatus, string> = {
  proposed: colorTokens.fgMuted,
  active: colorTokens.accent,
  validated: colorTokens.success,
  falsified: colorTokens.danger,
  expired: colorTokens.fgSubtle,
  superseded: colorTokens.fgSubtle,
};

function resolveBorderColor(node: GraphNode): string {
  if (node.is_hypothesis && node.hypothesis_status !== null) {
    return HYPOTHESIS_BORDER[node.hypothesis_status];
  }
  return colorTokens.line;
}

function resolveFillColor(node: GraphNode): string {
  return ENTITY_TYPE_COLORS[node.type] ?? colorTokens.fgMuted;
}

interface PositionedNode extends GraphNode {
  position: { x: number; y: number };
}

function layoutNodes(nodes: readonly GraphNode[]): PositionedNode[] {
  const hypothesisNodes = nodes.filter((node) => node.is_hypothesis);
  const otherNodes = nodes.filter((node) => !node.is_hypothesis);
  const stepX = 180;
  const stepY = 140;
  const columnWidth = Math.max(hypothesisNodes.length, otherNodes.length, 1);
  const positioned: PositionedNode[] = [];
  hypothesisNodes.forEach((node, index) => {
    positioned.push({
      ...node,
      position: {
        x: index * stepX - ((columnWidth - 1) * stepX) / 2,
        y: 0,
      },
    });
  });
  otherNodes.forEach((node, index) => {
    positioned.push({
      ...node,
      position: {
        x: index * stepX - ((columnWidth - 1) * stepX) / 2,
        y: stepY,
      },
    });
  });
  return positioned;
}

function toReactFlowNodes(positioned: readonly PositionedNode[]): Node[] {
  return positioned.map((node) => {
    const fill = resolveFillColor(node);
    const border = resolveBorderColor(node);
    const data: NodeRenderData = {
      label: node.label,
      type: node.type,
      isHypothesis: node.is_hypothesis,
      hypothesisStatus: node.hypothesis_status,
      belief: node.belief,
    };
    return {
      id: node.id,
      data,
      position: node.position,
      style: {
        background: node.is_hypothesis ? colorTokens.surface : colorTokens.surface,
        color: colorTokens.fg,
        border: `1px solid ${border}`,
        borderRadius: 4,
        padding: 8,
        fontSize: 11,
        fontFamily: "ui-monospace, monospace",
        minWidth: 140,
        boxShadow: node.is_hypothesis
          ? `inset 4px 0 0 ${fill}`
          : `inset 4px 0 0 ${fill}`,
      },
    } satisfies Node;
  });
}

function toReactFlowEdges(edges: readonly GraphEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.from_id,
    target: edge.to_id,
    label: edge.type,
    animated: edge.is_explicit,
    style: {
      stroke: edge.sign < 0 ? colorTokens.danger : colorTokens.line,
      strokeDasharray: edge.is_explicit ? undefined : "4 4",
    },
    labelStyle: {
      fill: colorTokens.fgMuted,
      fontSize: 9,
      fontFamily: "ui-monospace, monospace",
    },
    labelBgStyle: {
      fill: colorTokens.surface,
    },
  }));
}

export function KnowledgeGraph(props: KnowledgeGraphProps): ReactElement {
  const { graph } = props;
  const positioned = useMemo(
    () => layoutNodes(graph?.nodes ?? []),
    [graph?.nodes],
  );
  const reactFlowNodes = useMemo(
    () => toReactFlowNodes(positioned),
    [positioned],
  );
  const reactFlowEdges = useMemo(
    () => toReactFlowEdges(graph?.edges ?? []),
    [graph?.edges],
  );

  if (graph === null || graph.nodes.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>KNOWLEDGE GRAPH</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No entities or relations resolved for this run yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>KNOWLEDGE GRAPH</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-4 text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted mb-4">
          <span data-testid="knowledge-graph-summary">
            {graph.nodes.length} NODES · {graph.edges.length} EDGES
          </span>
        </div>
        <div
          className="border border-line/40 rounded-sm"
          style={{ width: "100%", height: 460 }}
          data-testid="knowledge-graph-canvas"
        >
          <ReactFlow
            nodes={reactFlowNodes}
            edges={reactFlowEdges}
            fitView
            proOptions={{ hideAttribution: true }}
            nodesDraggable
            nodesConnectable={false}
            edgesFocusable={false}
            elementsSelectable
          >
            <Background gap={18} size={1} color={colorTokens.line} />
            <Controls showInteractive={false} position="bottom-right" />
          </ReactFlow>
        </div>
        <ul
          className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs"
          data-testid="knowledge-graph-legend"
        >
          {graph.nodes.map((node) => (
            <li
              key={node.id}
              className="flex items-center gap-2 font-mono text-fg-muted"
            >
              <span
                className="inline-block w-2 h-2"
                style={{ background: resolveFillColor(node) }}
              />
              <span className="text-fg">{node.label}</span>
              <span className="text-fg-subtle uppercase">{node.type}</span>
              {node.is_hypothesis && node.belief !== null ? (
                <span className="text-accent-text font-mono tabular-nums">
                  belief {node.belief.toFixed(2)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
