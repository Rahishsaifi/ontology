import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorText, PageIntro } from "../components";

type Health = {
  status: string;
  demo_mode: boolean;
  graph_backend: string;
  accepts_demo_tokens: boolean;
  graph: { connected: boolean; backend: string; detail?: string };
  successfactors: {
    mode: string;
    credential_source: string;
    tls_verify: boolean;
    base_url?: string;
    read_only?: boolean;
  };
};

type Summary = {
  nodes?: number;
  relationships?: number;
  schema_classes?: number;
  demo_mode?: boolean;
};

export function OverviewPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [entityCount, setEntityCount] = useState<number | null>(null);
  const [metricsReady, setMetricsReady] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const next = await api<Health>("/api/health");
        if (cancelled) return;
        setHealth(next);
        const [graph, entities] = await Promise.all([
          api<Summary>("/api/graph/summary").catch(() => null),
          api<{ entities: unknown[] }>("/api/discovery/entities").catch(() => null),
        ]);
        if (cancelled) return;
        if (graph) setSummary(graph);
        if (entities) setEntityCount(entities.entities.length);
        setMetricsReady(true);
      } catch (caught) {
        if (!cancelled) {
          setError(caught);
          setMetricsReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <PageIntro
        kicker="Core HR workspace"
        title="Ontology"
        body="Discover the SuccessFactors schema (read-only), approve Core HR mappings, and load a durable knowledge graph. This app never deletes or updates records in SuccessFactors."
      />

      <ErrorText error={error} />

      {!health && !error ? <OverviewSkeleton /> : null}

      {health ? (
        <section className="hero-status panel overflow-hidden">
          <div className="border-b border-[var(--line)] bg-[linear-gradient(120deg,rgba(15,118,110,0.12),transparent_55%)] px-6 py-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="min-w-0 flex-1">
                <p className="muted text-xs font-medium uppercase tracking-[0.14em]">Connection status</p>
                <p className="brand-mark mt-2 text-2xl">{health.demo_mode ? "Synthetic demo" : "Live tenant"}</p>
                <p className="muted mt-2 max-w-xl text-sm">
                  Graph backend {health.graph_backend}
                  {health.graph.connected ? " is reachable" : " is not reachable"}
                  {health.graph.detail ? ` · ${health.graph.detail}` : ""}.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Signal ok={health.status === "ok"} label="API" />
                <Signal ok={health.graph.connected} label="Graph" />
                <Signal ok={health.successfactors.tls_verify} label="TLS" />
              </div>
            </div>
          </div>

          <div className="grid gap-0 sm:grid-cols-3">
            <Metric
              label="Discovered entities"
              value={entityCount == null ? "—" : String(entityCount)}
              hint="From the last metadata discovery"
              loading={!metricsReady}
            />
            <Metric
              label="Graph nodes"
              value={summary?.nodes == null ? "—" : String(summary.nodes)}
              hint="Imported SFEntity records"
              loading={!metricsReady}
            />
            <Metric
              label="Relationships"
              value={summary?.relationships == null ? "—" : String(summary.relationships)}
              hint="Approved business edges only"
              loading={!metricsReady}
            />
          </div>

          <div className="flex flex-wrap gap-3 border-t border-[var(--line)] px-6 py-4 text-sm">
            <Link className="linkish" to="/schema">
              Explore schema
            </Link>
            <span className="muted">·</span>
            <Link className="linkish" to="/ontology">
              Review ontology
            </Link>
            <span className="muted">·</span>
            <Link className="linkish" to="/ingestion">
              Import data
            </Link>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <section className="hero-status panel overflow-hidden" aria-busy="true" aria-label="Loading dashboard">
      <div className="border-b border-[var(--line)] bg-[linear-gradient(120deg,rgba(15,118,110,0.12),transparent_55%)] px-6 py-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0 flex-1 space-y-3">
            <span className="shimmer shimmer-line w-28" />
            <span className="shimmer shimmer-title" />
            <span className="shimmer shimmer-line max-w-xl w-full" />
            <span className="shimmer shimmer-line max-w-md w-4/5" />
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="shimmer shimmer-chip" />
            <span className="shimmer shimmer-chip" />
            <span className="shimmer shimmer-chip" />
          </div>
        </div>
      </div>
      <div className="grid gap-0 sm:grid-cols-3">
        {[0, 1, 2].map((key) => (
          <div key={key} className="border-[var(--line)] px-6 py-5 sm:border-r sm:last:border-r-0">
            <span className="shimmer shimmer-line w-32" />
            <span className="shimmer shimmer-metric" />
            <span className="shimmer shimmer-line mt-2 w-40" />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-3 border-t border-[var(--line)] px-6 py-4">
        <span className="shimmer shimmer-line w-24" />
        <span className="shimmer shimmer-line w-28" />
        <span className="shimmer shimmer-line w-20" />
      </div>
    </section>
  );
}

function Signal({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`status-chip ${ok ? "status-approved" : "status-rejected"}`}>
      {label}: {ok ? "ok" : "check"}
    </span>
  );
}

function Metric({
  label,
  value,
  hint,
  loading = false,
}: {
  label: string;
  value: string;
  hint: string;
  loading?: boolean;
}) {
  return (
    <div className="border-[var(--line)] px-6 py-5 sm:border-r sm:last:border-r-0">
      <p className="muted text-xs font-medium uppercase tracking-[0.1em]">{label}</p>
      {loading ? <span className="shimmer shimmer-metric" /> : <p className="brand-mark mt-2 text-3xl tracking-tight">{value}</p>}
      <p className="muted mt-1 text-xs">{hint}</p>
    </div>
  );
}
