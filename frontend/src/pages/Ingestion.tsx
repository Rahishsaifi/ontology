import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import {
  Button,
  CodeBlock,
  ErrorText,
  PageIntro,
  Panel,
  ProgressBar,
  Spinner,
  StatusBanner,
} from "../components";

const DEFAULT_SETS = [
  "User",
  "PerPerson",
  "EmpEmployment",
  "EmpJob",
  "FODepartment",
  "FOBusinessUnit",
  "FODivision",
  "Position",
  "FOCompany",
];

type EntityJobSummary = {
  status?: string;
  reason?: string;
  fetched?: number;
  failed?: number;
  upserted?: number;
  skipped?: number;
};

type JobRecord = {
  id: string;
  job_type: string;
  status: string;
  dry_run: boolean;
  mode?: string | null;
  entity_sets: string[];
  progress?: {
    entities_completed?: number;
    entities_total?: number;
  };
  summary?: {
    dry_run?: boolean;
    outcome?: string;
    hint?: string;
    entities?: Record<string, EntityJobSummary>;
    fatal?: string;
  };
  errors?: { message: string; entity_set?: string | null }[];
  finished_at?: string | null;
};

type BusyAction = "preview" | "dry_run" | "import" | null;

const TERMINAL = new Set(["succeeded", "partial", "failed"]);

export function IngestionPage() {
  const [selected, setSelected] = useState<string[]>(DEFAULT_SETS);
  const [preview, setPreview] = useState("");
  const [job, setJob] = useState<JobRecord | null>(null);
  const [busy, setBusy] = useState<BusyAction>(null);
  const [error, setError] = useState<unknown>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current != null) {
        window.clearInterval(pollRef.current);
      }
    };
  }, []);

  function toggle(name: string) {
    setSelected((current) => (current.includes(name) ? current.filter((item) => item !== name) : [...current, name]));
  }

  function stopPolling() {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function pollJob(jobId: string) {
    stopPolling();
    const tick = async () => {
      try {
        const next = await api<JobRecord>(`/api/ingestion/jobs/${encodeURIComponent(jobId)}`);
        setJob(next);
        if (TERMINAL.has(next.status)) {
          stopPolling();
          setBusy(null);
        }
      } catch (caught) {
        stopPolling();
        setBusy(null);
        setError(caught);
      }
    };
    void tick();
    pollRef.current = window.setInterval(() => {
      void tick();
    }, 900);
  }

  async function runPreview() {
    setError(null);
    setPreview("");
    const entity = selected[0];
    if (!entity) {
      setError(new Error("Select at least one entity set."));
      return;
    }
    setBusy("preview");
    try {
      const response = await api<Record<string, unknown>>("/api/ingestion/preview", {
        method: "POST",
        body: JSON.stringify({ entity_sets: [entity], limit: 2 }),
      });
      setPreview(JSON.stringify(response, null, 2));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(null);
    }
  }

  async function start(dryRun: boolean) {
    setError(null);
    setJob(null);
    stopPolling();
    if (!selected.length) {
      setError(new Error("Select at least one entity set."));
      return;
    }
    setBusy(dryRun ? "dry_run" : "import");
    try {
      const response = await api<JobRecord>("/api/ingestion/start", {
        method: "POST",
        body: JSON.stringify({ entity_sets: selected, dry_run: dryRun }),
      });
      setJob(response);
      if (TERMINAL.has(response.status)) {
        setBusy(null);
        return;
      }
      pollJob(response.id);
    } catch (caught) {
      setBusy(null);
      setError(caught);
    }
  }

  const completed = job?.progress?.entities_completed ?? 0;
  const total = job?.progress?.entities_total ?? selected.length;
  const running = busy === "dry_run" || busy === "import";
  const banner = jobBanner(job);

  return (
    <div>
      <PageIntro
        kicker="Import"
        title="Ingestion"
        body="Preview can run without Ontology approval. Dry run and Import only process approved classes — otherwise you get 0 rows. Dry runs leave the graph unchanged."
      />
      <Panel title="Entity selection">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {DEFAULT_SETS.map((name) => (
            <label
              key={name}
              className="flex items-center gap-2 border-b border-[var(--line)] py-2 text-sm last:border-b-0 sm:border-0 sm:py-1"
            >
              <input
                type="checkbox"
                checked={selected.includes(name)}
                disabled={busy != null}
                onChange={() => toggle(name)}
              />
              <span className="font-mono text-xs">{name}</span>
            </label>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button kind="quiet" onClick={runPreview} disabled={busy != null}>
            {busy === "preview" ? "Previewing…" : "Preview first selected"}
          </Button>
          <Button kind="quiet" onClick={() => start(true)} disabled={busy != null}>
            {busy === "dry_run" ? "Dry run running…" : "Dry run"}
          </Button>
          <Button onClick={() => start(false)} disabled={busy != null}>
            {busy === "import" ? "Importing…" : "Import"}
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {busy === "preview" ? <Spinner label="Loading preview…" /> : null}
          {running ? (
            <Spinner label={busy === "dry_run" ? "Validating selected entity sets…" : "Importing approved data into the graph…"} />
          ) : null}
          <ErrorText error={error} />
        </div>

        {job ? (
          <div className="mt-4 space-y-3">
            {banner ? <StatusBanner tone={banner.tone} title={banner.title} body={banner.body} /> : null}
            {(running || (job.progress && (job.progress.entities_total ?? 0) > 0)) && (
              <ProgressBar
                value={completed}
                max={Math.max(total, 1)}
                label={
                  running
                    ? `Processing entity sets (${completed} of ${total})…`
                    : `Entity sets processed: ${completed} of ${total}`
                }
              />
            )}
            <p className="muted text-xs">
              Job <span className="font-mono">{job.id.slice(0, 8)}</span> · status{" "}
              <strong>{job.status}</strong>
              {job.dry_run ? " · dry run (graph unchanged)" : " · write to graph"}
            </p>
            <details>
              <summary className="linkish cursor-pointer text-sm">Job details</summary>
              <div className="mt-2">
                <CodeBlock>{JSON.stringify(job, null, 2)}</CodeBlock>
              </div>
            </details>
          </div>
        ) : null}

        {preview ? (
          <div className="mt-4">
            <p className="muted mb-2 text-xs font-medium uppercase tracking-[0.08em]">Preview result</p>
            <CodeBlock soft>{preview}</CodeBlock>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function jobBanner(job: JobRecord | null): { tone: "info" | "success" | "warn" | "danger"; title: string; body: string } | null {
  if (!job) return null;
  const entitySummary = job.summary?.entities || {};
  const rows = Object.entries(entitySummary);
  const fetched = rows.reduce((sum, [, row]) => sum + (row.fetched || 0), 0);
  const upserted = rows.reduce((sum, [, row]) => sum + (row.upserted || 0), 0);
  const skipped = rows.filter(([, row]) => row.status === "skipped").length;
  const failed = rows.filter(([, row]) => row.status === "failed" || row.status === "incomplete").length;
  const perEntity = rows
    .map(([name, row]) => {
      const reason = row.reason ? ` (${row.reason})` : "";
      return `${name}: ${row.status || "unknown"}${reason}, fetched ${row.fetched || 0}`;
    })
    .join(" · ");
  const hint = job.summary?.hint;
  const outcome = job.summary?.outcome;

  if (job.status === "pending" || job.status === "running") {
    return {
      tone: "info",
      title: job.dry_run ? "Dry run in progress" : "Import in progress",
      body: "Buttons stay disabled until this job finishes. You can leave this page open and watch the bar fill.",
    };
  }
  if (outcome === "all_skipped_not_approved" || (job.status === "partial" && skipped > 0 && fetched === 0 && upserted === 0)) {
    return {
      tone: "warn",
      title: "Finished, but nothing was imported",
      body:
        hint ||
        `Fetched rows: 0. ${skipped} entity set(s) were skipped (usually not approved in Ontology). ${perEntity || "Open Job details."}`,
    };
  }
  if (outcome === "empty_fetch" || (job.status !== "failed" && fetched === 0 && upserted === 0 && skipped === 0)) {
    return {
      tone: "warn",
      title: job.dry_run ? "Dry run finished with 0 rows" : "Import finished with 0 rows",
      body: hint || `SuccessFactors returned no rows for the selected sets. ${perEntity || "Open Job details."}`,
    };
  }
  if (job.status === "succeeded") {
    return {
      tone: "success",
      title: job.dry_run ? "Dry run finished successfully" : "Import finished successfully",
      body: job.dry_run
        ? `Validated ${job.entity_sets.length} entity set(s). No graph writes. Fetched rows: ${fetched}. Skipped: ${skipped}. ${perEntity}`
        : `Wrote approved data. Fetched rows: ${fetched}. Upserted: ${upserted}. Open Graph or Query next. ${perEntity}`,
    };
  }
  if (job.status === "partial") {
    return {
      tone: "warn",
      title: "Job finished with partial results",
      body: `Fetched ${fetched}, upserted ${upserted}, skipped ${skipped}, failed ${failed}. ${hint || perEntity || "Check Job details below."}`,
    };
  }
  if (job.status === "failed") {
    const firstError = job.errors?.[0]?.message || job.summary?.fatal || "See Job details for errors.";
    return {
      tone: "danger",
      title: job.dry_run ? "Dry run failed" : "Import failed",
      body: firstError,
    };
  }
  return {
    tone: "info",
    title: `Job status: ${job.status}`,
    body: perEntity || "See Job details for the full record.",
  };
}
