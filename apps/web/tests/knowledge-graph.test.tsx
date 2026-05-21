import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { KnowledgeGraph } from "@/components/research/knowledge-graph";
import type { components } from "@/lib/api";

type RunGraph = components["schemas"]["RunGraph"];

beforeEach(() => {
  if (typeof window.DOMMatrixReadOnly === "undefined") {
    class DOMMatrixReadOnlyStub {
      constructor(_init?: string | number[]) {
        return;
      }
    }
    Object.defineProperty(window, "DOMMatrixReadOnly", {
      configurable: true,
      writable: true,
      value: DOMMatrixReadOnlyStub,
    });
  }
});

vi.mock("@xyflow/react", async () => {
  return {
    ReactFlow: ({ nodes, edges, children }: {
      nodes: Array<{ id: string; data: { label: string } }>;
      edges: Array<{ id: string; label?: string }>;
      children?: unknown;
    }) => (
      <div data-testid="reactflow-mock">
        <span data-testid="reactflow-node-count">{nodes.length}</span>
        <span data-testid="reactflow-edge-count">{edges.length}</span>
        <ul>
          {nodes.map((node) => (
            <li key={node.id} data-testid="reactflow-node">
              {node.data.label}
            </li>
          ))}
        </ul>
        <ul>
          {edges.map((edge) => (
            <li key={edge.id} data-testid="reactflow-edge">
              {edge.label}
            </li>
          ))}
        </ul>
        {children as React.ReactNode}
      </div>
    ),
    Background: () => null,
    Controls: () => null,
  };
});

const RUN_ID = "11111111-1111-4111-8111-111111111111";

function makeGraph(overrides: Partial<RunGraph> = {}): RunGraph {
  return {
    run_id: RUN_ID,
    nodes: [
      {
        id: "22222222-2222-4222-8222-222222222222",
        type: "hypothesis",
        label: "claim 1",
        is_hypothesis: true,
        hypothesis_id: "44444444-4444-4444-8444-444444444444",
        hypothesis_status: "active",
        belief: 0.65,
      },
      {
        id: "33333333-3333-4333-8333-333333333333",
        type: "company",
        label: "ScopeCo",
        is_hypothesis: false,
        hypothesis_id: null,
        hypothesis_status: null,
        belief: null,
      },
    ],
    edges: [
      {
        id: "55555555-5555-4555-8555-555555555555",
        from_id: "33333333-3333-4333-8333-333333333333",
        to_id: "22222222-2222-4222-8222-222222222222",
        type: "supports_hypothesis",
        quote: "supporting quote",
        sign: 1,
        is_explicit: true,
      },
    ],
    ...overrides,
  };
}

describe("KnowledgeGraph", () => {
  it("renders an empty placeholder when the graph has no nodes", () => {
    render(<KnowledgeGraph graph={null} />);
    expect(
      screen.getByText("No entities or relations resolved for this run yet."),
    ).toBeInTheDocument();
  });

  it("renders the summary line with node and edge counts", () => {
    render(<KnowledgeGraph graph={makeGraph()} />);
    const summary = screen.getByTestId("knowledge-graph-summary");
    expect(summary.textContent).toContain("2 NODES");
    expect(summary.textContent).toContain("1 EDGES");
  });

  it("passes nodes and edges to the react-flow canvas", () => {
    render(<KnowledgeGraph graph={makeGraph()} />);
    expect(screen.getByTestId("reactflow-node-count").textContent).toBe("2");
    expect(screen.getByTestId("reactflow-edge-count").textContent).toBe("1");
    const nodes = screen.getAllByTestId("reactflow-node");
    expect(nodes[0]?.textContent).toBe("claim 1");
    expect(nodes[1]?.textContent).toBe("ScopeCo");
    expect(screen.getByTestId("reactflow-edge").textContent).toBe(
      "supports_hypothesis",
    );
  });

  it("renders a legend row per node showing belief for hypothesis nodes", () => {
    render(<KnowledgeGraph graph={makeGraph()} />);
    const legend = screen.getByTestId("knowledge-graph-legend");
    expect(legend.textContent).toContain("claim 1");
    expect(legend.textContent).toContain("belief 0.65");
    expect(legend.textContent).toContain("ScopeCo");
  });
});
