import { useState } from "react";
import { api } from "../api";
import { Button, CodeBlock, ErrorText, PageIntro, Panel } from "../components";

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

export function IngestionPage() {
  const [selected, setSelected] = useState<string[]>(DEFAULT_SETS);
  const [preview, setPreview] = useState("");
  const [job, setJob] = useState("");
  const [error, setError] = useState<unknown>(null);

  function toggle(name: string) {
    setSelected((current) => (current.includes(name) ? current.filter((item) => item !== name) : [...current, name]));
  }

  async function runPreview() {
    setError(null);
    const entity = selected[0];
    if (!entity) return;
    try {
      const response = await api<Record<string, unknown>>("/api/ingestion/preview", {
        method: "POST",
        body: JSON.stringify({ entity_sets: [entity], limit: 2 }),
      });
      setPreview(JSON.stringify(response, null, 2));
    } catch (caught) {
      setError(caught);
    }
  }

  async function start(dryRun: boolean) {
    setError(null);
    try {
      const response = await api<Record<string, unknown>>("/api/ingestion/start", {
        method: "POST",
        body: JSON.stringify({ entity_sets: selected, dry_run: dryRun }),
      });
      setJob(JSON.stringify(response, null, 2));
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <div>
      <PageIntro
        kicker="Import"
        title="Ingestion"
        body="Only approved classes are written. Dry runs leave the graph unchanged. Sensitive and rejected properties stay out of the preview."
      />
      <Panel title="Entity selection">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {DEFAULT_SETS.map((name) => (
            <label key={name} className="flex items-center gap-2 border-b border-[var(--line)] py-2 text-sm last:border-b-0 sm:border-0 sm:py-1">
              <input type="checkbox" checked={selected.includes(name)} onChange={() => toggle(name)} />
              <span className="font-mono text-xs">{name}</span>
            </label>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button kind="quiet" onClick={runPreview}>
            Preview first selected
          </Button>
          <Button kind="quiet" onClick={() => start(true)}>
            Dry run
          </Button>
          <Button onClick={() => start(false)}>Import</Button>
        </div>
        <div className="mt-3">
          <ErrorText error={error} />
        </div>
        {preview ? (
          <div className="mt-4">
            <CodeBlock soft>{preview}</CodeBlock>
          </div>
        ) : null}
        {job ? (
          <div className="mt-4">
            <CodeBlock>{job}</CodeBlock>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
