import { useState } from "react";
import { api } from "../api";
import { Button, CodeBlock, ErrorText, PageIntro, Panel } from "../components";

type EntityRow = {
  entity_set: string;
  entity_type: string;
  key: string[];
  key_defined: boolean;
  property_count: number;
  navigation_count: number;
  unresolved_relationships: number;
};

export function SchemaPage() {
  const [rows, setRows] = useState<EntityRow[]>([]);
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState("");
  const [origin, setOrigin] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function discover() {
    setError(null);
    try {
      const discovered = await api<{ origin: string }>("/api/discovery/run", { method: "POST" });
      setOrigin(discovered.origin);
      await load(query);
    } catch (caught) {
      setError(caught);
    }
  }

  async function load(q: string) {
    const catalog = await api<{ entities: EntityRow[]; origin: string }>(
      `/api/discovery/entities?q=${encodeURIComponent(q)}`,
    );
    setRows(catalog.entities);
    setOrigin(catalog.origin);
  }

  async function openEntity(name: string) {
    setError(null);
    try {
      const entity = await api<Record<string, unknown>>(`/api/discovery/entities/${encodeURIComponent(name)}`);
      setDetail(JSON.stringify(entity, null, 2));
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <div className="space-y-4">
      <PageIntro
        kicker="Discovery"
        title="Schema"
        body="Entity sets, keys, and navigation properties come from the downloaded $metadata document, not from a fixed Core HR checklist."
      />
      <Panel title="Entity catalog" action={<Button onClick={discover}>Discover metadata</Button>}>
        <p className="muted mb-3 text-sm">Origin: {origin || "not discovered yet"}</p>
        <div className="mb-4 flex flex-wrap gap-2">
          <input
            className="field max-w-sm"
            value={query}
            placeholder="Filter entity sets"
            onChange={(event) => setQuery(event.target.value)}
          />
          <Button kind="quiet" onClick={() => load(query).catch(setError)}>
            Search
          </Button>
        </div>
        <ErrorText error={error} />
        <div className="overflow-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Entity set</th>
                <th>Type</th>
                <th>Key</th>
                <th>Properties</th>
                <th>Unresolved</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.entity_set}>
                  <td>
                    <button className="linkish" onClick={() => openEntity(row.entity_set)}>
                      {row.entity_set}
                    </button>
                  </td>
                  <td className="font-mono text-xs">{row.entity_type}</td>
                  <td>{row.key_defined ? row.key.join(", ") : "missing"}</td>
                  <td>{row.property_count}</td>
                  <td>
                    {row.unresolved_relationships}/{row.navigation_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {detail ? (
        <Panel title="Entity detail" lead="Keys, properties, and navigation properties for the selected set.">
          <CodeBlock soft>{detail}</CodeBlock>
        </Panel>
      ) : null}
    </div>
  );
}
