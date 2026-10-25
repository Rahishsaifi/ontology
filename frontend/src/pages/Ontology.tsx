import { useMemo, useState } from "react";
import sampleMappings from "../../../samples/reviewed-mappings.json";
import { api } from "../api";
import { Button, ErrorText, PageIntro, PaginationBar, Panel, Spinner, pageSlice, statusClass } from "../components";

type OntologyClass = {
  class_id: string;
  source_entity_type: string;
  source_entity_set: string | null;
  canonical_name: string | null;
  status: string;
  inference_note: string | null;
  key_defined: boolean;
};

type OntologyRelationship = {
  relationship_id: string;
  source_entity: string;
  navigation_property: string;
  target_entity: string | null;
  relationship_semantics: string | null;
  relationship_type: string | null;
  mapping_status: string;
  key_resolution: string;
  inference_note: string | null;
};

type Ontology = {
  classes: OntologyClass[];
  relationships: OntologyRelationship[];
  concept_coverage: Record<string, string>;
  mapping_version: number;
};

const PAGE_SIZE = 20;

export function OntologyPage() {
  const [ontology, setOntology] = useState<Ontology | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState("Reviewed in Ontology Studio.");
  const [generating, setGenerating] = useState(false);
  const [classQuery, setClassQuery] = useState("");
  const [relQuery, setRelQuery] = useState("");
  const [classPage, setClassPage] = useState(1);
  const [relPage, setRelPage] = useState(1);

  const filteredClasses = useMemo(() => {
    if (!ontology) return [];
    const q = classQuery.trim().toLowerCase();
    if (!q) return ontology.classes;
    return ontology.classes.filter((item) => {
      const haystack = [
        item.source_entity_set,
        item.source_entity_type,
        item.canonical_name,
        item.status,
        item.inference_note,
        item.class_id,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [ontology, classQuery]);

  const filteredRels = useMemo(() => {
    if (!ontology) return [];
    const q = relQuery.trim().toLowerCase();
    if (!q) return ontology.relationships;
    return ontology.relationships.filter((item) => {
      const haystack = [
        item.navigation_property,
        item.source_entity,
        item.target_entity,
        item.relationship_type,
        item.relationship_semantics,
        item.mapping_status,
        item.inference_note,
        item.relationship_id,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [ontology, relQuery]);

  const classRows = pageSlice(filteredClasses, classPage, PAGE_SIZE);
  const relRows = pageSlice(filteredRels, relPage, PAGE_SIZE);

  async function generate() {
    setError(null);
    setGenerating(true);
    try {
      setOntology(await api<Ontology>("/api/ontology/generate", { method: "POST" }));
      setClassPage(1);
      setRelPage(1);
    } catch (caught) {
      setError(caught);
    } finally {
      setGenerating(false);
    }
  }

  async function importSample() {
    setError(null);
    try {
      setOntology(
        await api<Ontology>("/api/ontology/mappings/import", {
          method: "POST",
          body: JSON.stringify(sampleMappings),
        }),
      );
      setClassPage(1);
      setRelPage(1);
    } catch (caught) {
      setError(caught);
    }
  }

  async function decide(id: string, action: "approve" | "reject", body: Record<string, unknown>) {
    setError(null);
    try {
      const response = await api<{ ontology?: Ontology } | Ontology>(
        `/api/ontology/mappings/${encodeURIComponent(id)}/${action}`,
        {
          method: "POST",
          body: JSON.stringify({ ...body, note }),
        },
      );
      const next = "ontology" in response && response.ontology ? response.ontology : (response as Ontology);
      setOntology(next);
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <div className="space-y-4">
      <PageIntro
        kicker="Review"
        title="Ontology"
        body="Structural facts are discovered automatically. Business meanings stay draft until you approve them. Approvals only affect this app’s mapping store and Neo4j — never SuccessFactors data."
      />
      <Panel
        title="Studio"
        lead="Importing the sample review approves the synthetic Core HR mappings, including User as UserAccount."
        action={
          <>
            <Button onClick={generate} disabled={generating}>
              {generating ? "Generating…" : "Generate draft"}
            </Button>
            <Button kind="quiet" onClick={importSample} disabled={generating}>
              Import sample review
            </Button>
          </>
        }
      >
        <label className="block text-sm">
          <span className="muted mb-1 block text-xs font-medium uppercase tracking-[0.08em]">Review note</span>
          <input className="field" value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {generating ? <Spinner label="Generating ontology draft from discovered metadata…" /> : null}
          <ErrorText error={error} />
        </div>
        {ontology ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(ontology.concept_coverage).map(([concept, value]) => (
              <span key={concept} className="status-chip status-default">
                {concept}: {value}
              </span>
            ))}
          </div>
        ) : null}
      </Panel>

      {ontology ? (
        <>
          <Panel
            title="Classes"
            lead={`${filteredClasses.length} of ${ontology.classes.length} classes${classQuery.trim() ? " matching filter" : ""}.`}
          >
            <div className="mb-3">
              <input
                className="field max-w-md"
                value={classQuery}
                placeholder="Search classes (entity set, type, status, canonical…)"
                onChange={(event) => {
                  setClassQuery(event.target.value);
                  setClassPage(1);
                }}
              />
            </div>
            <div className="divide-y divide-[var(--line)]">
              {classRows.map((item) => (
                <article key={item.class_id} className="flex flex-wrap items-start justify-between gap-3 py-4 first:pt-0 last:pb-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong>{item.source_entity_set || item.source_entity_type}</strong>
                      <span className={statusClass(item.status)}>{item.status}</span>
                      <span className="muted text-sm">{item.canonical_name || "no canonical concept"}</span>
                    </div>
                    <p className="muted mt-1 text-sm">{item.inference_note}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      onClick={() =>
                        decide(item.class_id, "approve", {
                          canonical_name: item.canonical_name || "UserAccount",
                        })
                      }
                      disabled={!item.key_defined}
                    >
                      Approve
                    </Button>
                    <Button kind="danger" onClick={() => decide(item.class_id, "reject", {})}>
                      Reject
                    </Button>
                  </div>
                </article>
              ))}
              {classRows.length === 0 ? <p className="muted py-2 text-sm">No classes match this search.</p> : null}
            </div>
            <PaginationBar page={classPage} pageSize={PAGE_SIZE} total={filteredClasses.length} onPageChange={setClassPage} />
          </Panel>
          <Panel
            title="Relationships"
            lead={`${filteredRels.length} of ${ontology.relationships.length} relationships${relQuery.trim() ? " matching filter" : ""}.`}
          >
            <div className="mb-3">
              <input
                className="field max-w-md"
                value={relQuery}
                placeholder="Search relationships (nav, source, target, status…)"
                onChange={(event) => {
                  setRelQuery(event.target.value);
                  setRelPage(1);
                }}
              />
            </div>
            <div className="divide-y divide-[var(--line)]">
              {relRows.map((item) => (
                <article key={item.relationship_id} className="flex flex-wrap items-start justify-between gap-3 py-4 first:pt-0 last:pb-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong>{item.navigation_property}</strong>
                      <span className={statusClass(item.mapping_status)}>{item.mapping_status}</span>
                      <span className="text-sm">{item.relationship_type || item.relationship_semantics || "unmapped"}</span>
                    </div>
                    <p className="muted mt-1 text-sm">
                      {item.source_entity} → {item.target_entity || "unresolved"} · key {item.key_resolution}
                    </p>
                    <p className="muted text-sm">{item.inference_note}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      disabled={!item.relationship_semantics || item.mapping_status === "unresolved"}
                      onClick={() =>
                        decide(item.relationship_id, "approve", {
                          relationship_type: item.relationship_semantics,
                        })
                      }
                    >
                      Approve
                    </Button>
                    <Button kind="danger" onClick={() => decide(item.relationship_id, "reject", {})}>
                      Reject
                    </Button>
                  </div>
                </article>
              ))}
              {relRows.length === 0 ? <p className="muted py-2 text-sm">No relationships match this search.</p> : null}
            </div>
            <PaginationBar page={relPage} pageSize={PAGE_SIZE} total={filteredRels.length} onPageChange={setRelPage} />
          </Panel>
        </>
      ) : null}
    </div>
  );
}
