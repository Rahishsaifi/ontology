import { useState } from "react";
import { api } from "../api";
import { Button, CodeBlock, ErrorText, PageIntro, Panel } from "../components";

export function SyncPage() {
  const [entitySets, setEntitySets] = useState("EmpJob");
  const [history, setHistory] = useState("");
  const [job, setJob] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function loadHistory() {
    setError(null);
    try {
      setHistory(JSON.stringify(await api("/api/sync/history"), null, 2));
    } catch (caught) {
      setError(caught);
    }
  }

  async function start(mode: "full" | "incremental") {
    setError(null);
    try {
      const response = await api("/api/sync/start", {
        method: "POST",
        body: JSON.stringify({
          entity_sets: entitySets
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          mode,
          dry_run: false,
        }),
      });
      setJob(JSON.stringify(response, null, 2));
      await loadHistory();
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <div>
      <PageIntro
        kicker="Keep current"
        title="Synchronization"
        body="Incremental sync uses the last successful watermark and lastModifiedDateTime. An empty or failed read does not delete existing graph data."
      />
      <Panel title="Sync controls" action={<Button kind="quiet" onClick={loadHistory}>Refresh history</Button>}>
        <label className="block text-sm">
          <span className="muted mb-1 block text-xs font-medium uppercase tracking-[0.08em]">Entity sets</span>
          <input className="field" value={entitySets} onChange={(event) => setEntitySets(event.target.value)} />
        </label>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => start("full")}>Full sync</Button>
          <Button kind="quiet" onClick={() => start("incremental")}>
            Incremental sync
          </Button>
        </div>
        <div className="mt-3">
          <ErrorText error={error} />
        </div>
        {job ? (
          <div className="mt-4">
            <CodeBlock>{job}</CodeBlock>
          </div>
        ) : null}
        {history ? (
          <div className="mt-4 max-h-96 overflow-auto">
            <CodeBlock soft>{history}</CodeBlock>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
