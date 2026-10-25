import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import { useState } from "react";
import "@xyflow/react/dist/style.css";
import { api } from "../api";
import { Button, CodeBlock, ErrorText, PageIntro, Panel } from "../components";

type GraphNode = {
  entity_type: string;
  source_key: string;
  display_label: string;
  canonical_class: string | null;
  effective_start: string | null;
  provenance: string;
};

type Neighborhood = {
  nodes: GraphNode[];
  edges: {
    relationship_type: string;
    source_entity_type: string | null;
    source_key: string | null;
    target_entity_type: string | null;
    target_key: string | null;
  }[];
};

export function GraphPage() {
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [entityType, setEntityType] = useState("");
  const [flowNodes, setFlowNodes] = useState<Node[]>([]);
  const [flowEdges, setFlowEdges] = useState<Edge[]>([]);
  const [error, setError] = useState<unknown>(null);

  async function refresh() {
    setError(null);
    try {
      const [nextSummary, nextNodes] = await Promise.all([
        api<Record<string, unknown>>("/api/graph/summary"),
        api<{ nodes: GraphNode[] }>(
          `/api/graph/nodes?entity_type=${encodeURIComponent(entityType)}&limit=50`,
        ),
      ]);
      setSummary(nextSummary);
      setNodes(nextNodes.nodes);
    } catch (caught) {
      setError(caught);
    }
  }

  async function openNeighborhood(node: GraphNode) {
    setError(null);
    try {
      const graph = await api<Neighborhood>(
        `/api/graph/neighborhood/${encodeURIComponent(node.entity_type)}/${encodeURIComponent(node.source_key)}`,
      );
      const positioned: Node[] = graph.nodes.map((item, index) => ({
        id: `${item.entity_type}|${item.source_key}`,
        position: { x: (index % 3) * 250, y: Math.floor(index / 3) * 130 },
        data: { label: `${item.display_label || item.source_key}\n${item.entity_type}` },
        style: {
          width: 220,
          fontSize: 12,
          whiteSpace: "pre-wrap",
          border: "1px solid rgba(11,31,42,0.14)",
          borderRadius: 8,
          background: "rgba(255,255,255,0.95)",
          padding: 8,
          color: "#0b1f2a",
        },
      }));
      const edges: Edge[] = graph.edges
        .filter((edge) => edge.source_entity_type && edge.source_key && edge.target_entity_type && edge.target_key)
        .map((edge, index) => ({
          id: `${edge.relationship_type}-${index}`,
          source: `${edge.source_entity_type}|${edge.source_key}`,
          target: `${edge.target_entity_type}|${edge.target_key}`,
          label: edge.relationship_type,
          style: { stroke: "#0f766e" },
          labelStyle: { fill: "#1a3644", fontSize: 11 },
        }));
      setFlowNodes(positioned);
      setFlowEdges(edges);
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <div className="space-y-4">
      <PageIntro
        kicker="Knowledge graph"
        title="Explorer"
        body="Browse imported nodes, then expand a neighborhood to inspect approved relationships and provenance."
      />
      <Panel title="Nodes" action={<Button onClick={refresh}>Refresh</Button>}>
        <div className="mb-4 flex flex-wrap gap-2">
          <input
            className="field max-w-md"
            placeholder="Entity type filter, for example SFOData.EmpJob"
            value={entityType}
            onChange={(event) => setEntityType(event.target.value)}
          />
        </div>
        <ErrorText error={error} />
        {summary ? (
          <div className="mb-4">
            <CodeBlock soft>{JSON.stringify(summary, null, 2)}</CodeBlock>
          </div>
        ) : null}
        <ul className="space-y-2 text-sm">
          {nodes.map((node) => (
            <li key={`${node.entity_type}|${node.source_key}`} className="flex flex-wrap items-baseline gap-2 border-b border-[var(--line)] py-2 last:border-b-0">
              <button className="linkish" onClick={() => openNeighborhood(node)}>
                {node.display_label || node.source_key}
              </button>
              <span className="muted">{node.canonical_class || node.entity_type}</span>
              {node.effective_start ? <span className="muted">· {node.effective_start}</span> : null}
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Neighborhood" lead="Click a node above to expand connected relationships.">
        <div className="h-[28rem] overflow-hidden rounded-[8px] border border-[var(--line)] bg-[rgba(255,255,255,0.55)]">
          <ReactFlow className="h-full w-full" nodes={flowNodes} edges={flowEdges} fitView>
            <Background gap={18} color="rgba(11,31,42,0.08)" />
            <Controls />
          </ReactFlow>
        </div>
      </Panel>
    </div>
  );
}
