import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, CodeBlock, ErrorText, PageIntro, Panel } from "../components";

type QueryDef = { id: string; name: string; description: string; cypher: string };

export function QueryPage() {
  const [queries, setQueries] = useState<QueryDef[]>([]);
  const [engine, setEngine] = useState("");
  const [queryId, setQueryId] = useState("reporting-lines");
  const [cypher, setCypher] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api<{ queries: QueryDef[]; engine: string }>("/api/graph/queries")
      .then((payload) => {
        setQueries(payload.queries);
        setEngine(payload.engine);
        if (payload.queries[0]) setQueryId(payload.queries[0].id);
      })
      .catch(setError);
  }, []);

  async function runLibrary() {
    setError(null);
    try {
      const response = await api<Record<string, unknown>>("/api/graph/query", {
        method: "POST",
        body: JSON.stringify({ query_id: queryId, parameters: { limit: 20 } }),
      });
      setResult(JSON.stringify(response, null, 2));
    } catch (caught) {
      setError(caught);
    }
  }

  async function runCypher() {
    setError(null);
    try {
      const response = await api<Record<string, unknown>>("/api/graph/query", {
        method: "POST",
        body: JSON.stringify({ cypher, parameters: {} }),
      });
      setResult(JSON.stringify(response, null, 2));
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <div>
      <PageIntro
        kicker="Read-only"
        title="Query"
        body={`Engine: ${engine || "unknown"}. Saved queries work on memory or Neo4j. Raw Cypher is accepted only by Neo4j, as a single read-only statement.`}
      />
      <Panel title="Library and Cypher">
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-[14rem] flex-1 text-sm">
            <span className="muted mb-1 block text-xs font-medium uppercase tracking-[0.08em]">Saved query</span>
            <select className="field" value={queryId} onChange={(event) => setQueryId(event.target.value)}>
              {queries.map((query) => (
                <option key={query.id} value={query.id}>
                  {query.name}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={runLibrary}>Run saved query</Button>
        </div>
        <p className="muted mt-2 text-sm">{queries.find((query) => query.id === queryId)?.description}</p>
        <label className="mt-5 block text-sm">
          <span className="muted mb-1 block text-xs font-medium uppercase tracking-[0.08em]">Read-only Cypher</span>
          <textarea
            className="field h-32 font-mono text-xs"
            value={cypher}
            onChange={(event) => setCypher(event.target.value)}
            placeholder="MATCH (n:SFEntity) RETURN n.entityType, count(n) LIMIT 20"
          />
        </label>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button kind="quiet" onClick={runCypher}>
            Run Cypher
          </Button>
          <ErrorText error={error} />
        </div>
        {result ? (
          <div className="mt-4">
            <CodeBlock>{result}</CodeBlock>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
