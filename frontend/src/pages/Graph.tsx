import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  MarkerType,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import "@xyflow/react/dist/style.css";
import { api } from "../api";
import { Button, ErrorText, PageIntro, Panel, Spinner, StatusBanner } from "../components";

type GraphNode = {
  identity?: string;
  entity_type: string;
  source_key: string;
  display_label: string;
  canonical_class: string | null;
  effective_start: string | null;
  provenance: string;
};

type GraphEdge = {
  relationship_type: string;
  mapping_id?: string | null;
  source_entity_type: string | null;
  source_key: string | null;
  target_entity_type: string | null;
  target_key: string | null;
};

type Summary = {
  nodes?: number;
  relationships?: number;
  by_entity_type?: { entity_type: string; count: number }[];
  by_relationship?: { relationship_type: string; count: number }[];
};

type ExploreResponse = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  note?: string | null;
};

const TYPE_COLORS: Record<string, string> = {
  "SFOData.User": "#0f766e",
  "SFOData.EmpJob": "#1d4ed8",
  "SFOData.EmpEmployment": "#7c3aed",
  "SFOData.PerPerson": "#b45309",
  "SFOData.FODepartment": "#be123c",
  "SFOData.Position": "#0e7490",
};

function shortType(entityType: string): string {
  return entityType.replace(/^SFOData\./, "");
}

function nodeId(node: Pick<GraphNode, "entity_type" | "source_key">): string {
  return `${node.entity_type}|${node.source_key}`;
}

function layoutNodes(items: GraphNode[]): Node[] {
  const buckets = new Map<string, GraphNode[]>();
  for (const item of items) {
    const key = item.entity_type;
    const list = buckets.get(key) || [];
    list.push(item);
    buckets.set(key, list);
  }
  const columns = [...buckets.keys()].sort();
  const positioned: Node[] = [];
  columns.forEach((entityType, column) => {
    const color = TYPE_COLORS[entityType] || "#334155";
    (buckets.get(entityType) || []).forEach((item, row) => {
      const title = item.display_label || item.source_key;
      const concept = item.canonical_class ? ` · ${item.canonical_class}` : "";
      positioned.push({
        id: nodeId(item),
        position: { x: column * 280, y: row * 110 },
        data: {
          label: `${title}\n${shortType(item.entity_type)}${concept}`,
        },
        style: {
          width: 230,
          fontSize: 12,
          whiteSpace: "pre-wrap",
          border: `1px solid ${color}`,
          borderLeft: `4px solid ${color}`,
          borderRadius: 10,
          background: "rgba(255,255,255,0.96)",
          padding: 10,
          color: "#0b1f2a",
          boxShadow: "0 1px 0 rgba(11,31,42,0.06)",
        },
      });
    });
  });
  return positioned;
}

function toFlowEdges(edges: GraphEdge[]): Edge[] {
  return edges
    .filter((edge) => edge.source_entity_type && edge.source_key && edge.target_entity_type && edge.target_key)
    .map((edge, index) => ({
      id: `${edge.relationship_type}-${edge.mapping_id || index}-${edge.source_key}-${edge.target_key}`,
      source: `${edge.source_entity_type}|${edge.source_key}`,
      target: `${edge.target_entity_type}|${edge.target_key}`,
      label: edge.relationship_type,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, color: "#0f766e" },
      style: { stroke: "#0f766e", strokeWidth: 1.5 },
      labelStyle: { fill: "#1a3644", fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: "rgba(255,255,255,0.9)" },
      labelBgPadding: [4, 2] as [number, number],
    }));
}

export function GraphPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [flowNodes, setFlowNodes] = useState<Node[]>([]);
  const [flowEdges, setFlowEdges] = useState<Edge[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [rawNodes, setRawNodes] = useState<GraphNode[]>([]);

  const typeOptions = useMemo(() => summary?.by_entity_type || [], [summary]);

  useEffect(() => {
    void loadSummaryAndExplore(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadSummaryAndExplore(preferCoreHr: boolean) {
    setError(null);
    setLoading(true);
    try {
      const nextSummary = await api<Summary>("/api/graph/summary");
      setSummary(nextSummary);
      const available = (nextSummary.by_entity_type || []).map((row) => row.entity_type);
      let types = selectedTypes.filter((item) => available.includes(item));
      if (preferCoreHr || types.length === 0) {
        const preferred = ["SFOData.User", "SFOData.EmpJob"].filter((item) => available.includes(item));
        types = preferred.length ? preferred : available.slice(0, 2);
        setSelectedTypes(types);
      }
      await loadExplore(types);
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }

  async function loadExplore(types: string[]) {
    const params = new URLSearchParams();
    if (types.length) params.set("entity_types", types.join(","));
    params.set("limit", "80");
    const graph = await api<ExploreResponse>(`/api/graph/explore?${params.toString()}`);
    setRawNodes(graph.nodes);
    setFlowNodes(layoutNodes(graph.nodes));
    setFlowEdges(toFlowEdges(graph.edges));
    setNote(graph.note || null);
    setSelectedNode(null);
  }

  function toggleType(entityType: string) {
    setSelectedTypes((current) => {
      const next = current.includes(entityType)
        ? current.filter((item) => item !== entityType)
        : [...current, entityType];
      return next;
    });
  }

  async function applyFilter() {
    setError(null);
    setLoading(true);
    try {
      await loadExplore(selectedTypes);
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }

  async function focusNeighborhood(node: GraphNode) {
    setError(null);
    setLoading(true);
    setSelectedNode(node);
    try {
      const graph = await api<ExploreResponse & { center?: GraphNode }>(
        `/api/graph/neighborhood/${encodeURIComponent(node.entity_type)}/${encodeURIComponent(node.source_key)}`,
      );
      setRawNodes(graph.nodes);
      setFlowNodes(layoutNodes(graph.nodes));
      setFlowEdges(toFlowEdges(graph.edges));
      setNote(
        graph.edges.length
          ? `Neighborhood around ${node.display_label || node.source_key}`
          : "This node has no approved relationship edges yet.",
      );
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <PageIntro
        kicker="Knowledge graph"
        title="Graph"
        body="Visual map of imported SuccessFactors entities and approved business links. UserAccount is the ontology label for User — not a separate SF entity."
      />

      <Panel
        title="Visual explorer"
        lead="Boxes are people/jobs/org units. Lines are approved relationships (HAS_JOB, REPORTS_TO, …). Click a node to zoom into its neighborhood."
        action={
          <>
            <Button kind="quiet" onClick={() => loadSummaryAndExplore(false)} disabled={loading}>
              Refresh
            </Button>
            <Button onClick={applyFilter} disabled={loading || selectedTypes.length === 0}>
              Draw graph
            </Button>
          </>
        }
      >
        <div className="mb-3 flex flex-wrap gap-2">
          {typeOptions.length === 0 ? (
            <p className="muted text-sm">No imported nodes yet. Run Ingestion on approved sets first.</p>
          ) : (
            typeOptions.map((row) => {
              const active = selectedTypes.includes(row.entity_type);
              return (
                <button
                  key={row.entity_type}
                  type="button"
                  className={`status-chip ${active ? "status-approved" : "status-default"}`}
                  onClick={() => toggleType(row.entity_type)}
                >
                  {shortType(row.entity_type)} · {row.count}
                </button>
              );
            })
          )}
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-3">
          {loading ? <Spinner label="Loading graph…" /> : null}
          <ErrorText error={error} />
          {summary ? (
            <p className="muted text-xs">
              Graph totals: {summary.nodes ?? 0} nodes · {summary.relationships ?? 0} relationships
            </p>
          ) : null}
        </div>

        {note ? <StatusBanner tone={flowEdges.length ? "info" : "warn"} title={note} /> : null}

        <div className="mt-3 h-[32rem] overflow-hidden rounded-[10px] border border-[var(--line)] bg-[rgba(255,255,255,0.7)]">
          {flowNodes.length === 0 && !loading ? (
            <div className="flex h-full items-center justify-center p-6 text-center">
              <p className="muted max-w-md text-sm">
                Nothing to draw yet. Import User and EmpJob, approve relationship mappings in Ontology, then click{" "}
                <strong>Draw graph</strong>.
              </p>
            </div>
          ) : (
            <ReactFlow
              className="h-full w-full"
              nodes={flowNodes}
              edges={flowEdges}
              fitView
              minZoom={0.2}
              onNodeClick={(_, node) => {
                const match = rawNodes.find((item) => nodeId(item) === node.id);
                if (match) void focusNeighborhood(match);
              }}
            >
              <Background gap={18} color="rgba(11,31,42,0.08)" />
              <MiniMap pannable zoomable />
              <Controls />
            </ReactFlow>
          )}
        </div>

        {selectedNode ? (
          <p className="muted mt-3 text-sm">
            Focused: <strong>{selectedNode.display_label || selectedNode.source_key}</strong> (
            {shortType(selectedNode.entity_type)}
            {selectedNode.canonical_class ? ` / ${selectedNode.canonical_class}` : ""})
          </p>
        ) : null}
      </Panel>

      {(summary?.by_relationship || []).length > 0 ? (
        <Panel title="Relationship types in Neo4j" lead="These are the edge kinds currently stored from approved mappings.">
          <div className="flex flex-wrap gap-2">
            {(summary?.by_relationship || []).map((row) => (
              <span key={row.relationship_type} className="status-chip status-default">
                {row.relationship_type}: {row.count}
              </span>
            ))}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
