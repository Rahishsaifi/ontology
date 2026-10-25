import { Link } from "react-router-dom";
import { PageIntro, Panel } from "../components";

const screens = [
  {
    n: "1",
    title: "Overview",
    path: "/",
    what: "Dashboard for connection health and high-level counts.",
    how: [
      "Confirm SuccessFactors and Graph indicators are green.",
      "Check discovered entity count and graph node/relationship totals.",
      "Use this screen as a status check before discovery or import.",
    ],
  },
  {
    n: "2",
    title: "Connect",
    path: "/connect",
    what: "Authenticate to SuccessFactors OData (read-only). Base URL can come from SF_BASE_URL in .env; paste the access token manually.",
    how: [
      "Base URL: your OData v2 URL (prefilled from .env when set).",
      "Auth: oauth_bearer + Postman access_token (or SAML / basic if needed).",
      "Click Test connection and keep “remember for session” on.",
      "Set DEMO_MODE=false in .env for live tenant data.",
      "Revisit this page if the session expires or credentials change.",
    ],
  },
  {
    n: "3",
    title: "Schema",
    path: "/schema",
    what: "Catalog of entity sets from the downloaded $metadata document — keys, properties, and navigations as they exist in your tenant.",
    how: [
      "Click Discover metadata to refresh the catalog.",
      "Search or open entity sets (for example User, EmpJob, FODepartment).",
      "Review keys, properties, and navigation properties in the detail panel.",
      "Use pagination when the list is long.",
    ],
  },
  {
    n: "4",
    title: "Ontology",
    path: "/ontology",
    what: "Proposed Core HR meanings for discovered types. Nothing is treated as business truth until you approve it. Ingestion only writes approved mappings.",
    how: [
      "Click Generate draft (a loader appears while metadata is mapped).",
      "Search and paginate the class / relationship lists.",
      "Approve classes and relationships you care about.",
      "Reject anything wrong or sensitive.",
      "Import sample review only in demo / synthetic mode — not for a live tenant.",
    ],
  },
  {
    n: "5",
    title: "Ingestion",
    path: "/ingestion",
    what: "Pulls approved entity sets from SuccessFactors (GET only) and writes them into Neo4j (or the memory graph).",
    how: [
      "Select Core HR sets (User, PerPerson, EmpEmployment, EmpJob, and related FO* sets).",
      "Preview first selected — confirm the payload looks right.",
      "Dry run — validates without writing to the graph.",
      "Import — loads approved data into Neo4j.",
    ],
  },
  {
    n: "6",
    title: "Graph",
    path: "/graph",
    what: "Browse imported SFEntity nodes and their approved business relationships.",
    how: [
      "Pick an entity type and click Refresh.",
      "Open a node to inspect its neighborhood (managers, org units, and so on).",
    ],
  },
  {
    n: "7",
    title: "Query",
    path: "/query",
    what: "Run saved graph questions or a single read-only Cypher statement against Neo4j.",
    how: [
      "Run a saved query (for example reporting lines).",
      "Or enter one read-only Cypher statement (Neo4j backend only).",
      "Writes, multi-statement batches, and dynamic labels from metadata are blocked.",
    ],
  },
  {
    n: "8",
    title: "Sync",
    path: "/sync",
    what: "Refresh graph data from SuccessFactors after the first import.",
    how: [
      "Incremental sync for updates after the first load.",
      "Full sync to refresh selected sets.",
      "Use Refresh history to see past jobs.",
    ],
  },
];

export function DocsPage() {
  return (
    <div className="space-y-4">
      <PageIntro
        kicker="Guide"
        title="Docs"
        body="What each screen is for, and how to use this platform end to end. SuccessFactors access is read-only: the app never creates, updates, or deletes tenant HR records."
      />

      <Panel title="What this platform does" lead="Discover schema → review ontology → load an approved knowledge graph.">
        <p className="text-sm leading-relaxed text-[var(--ink-soft)]">
          The app downloads SuccessFactors OData metadata and entity feeds with GET requests only. You review proposed
          Core HR mappings in Ontology Studio, then import approved sets into Neo4j. Mapping approvals and graph writes
          stay inside this application — they do not change data in SuccessFactors.
        </p>
        <ol className="mt-4 list-decimal space-y-1 pl-5 text-sm text-[var(--ink-soft)]">
          <li>
            Connect to the tenant and discover metadata (
            <Link className="linkish" to="/connect">
              Connect
            </Link>
            ,{" "}
            <Link className="linkish" to="/schema">
              Schema
            </Link>
            ).
          </li>
          <li>
            Generate and approve ontology mappings (
            <Link className="linkish" to="/ontology">
              Ontology
            </Link>
            ).
          </li>
          <li>
            Dry-run, then import into the graph (
            <Link className="linkish" to="/ingestion">
              Ingestion
            </Link>
            ).
          </li>
          <li>
            Explore and query (
            <Link className="linkish" to="/graph">
              Graph
            </Link>
            ,{" "}
            <Link className="linkish" to="/query">
              Query
            </Link>
            ), then keep data fresh with{" "}
            <Link className="linkish" to="/sync">
              Sync
            </Link>
            .
          </li>
        </ol>
      </Panel>

      <Panel title="Practical first path" lead="Recommended order when you already have a live connection and discovery.">
        <p className="text-sm leading-relaxed text-[var(--ink-soft)]">
          <Link className="linkish" to="/ontology">
            Ontology
          </Link>{" "}
          → approve Core HR →{" "}
          <Link className="linkish" to="/ingestion">
            Ingestion
          </Link>{" "}
          dry run → Import →{" "}
          <Link className="linkish" to="/graph">
            Graph
          </Link>{" "}
          →{" "}
          <Link className="linkish" to="/query">
            Query
          </Link>
          .
        </p>
      </Panel>

      {screens.map((screen) => (
        <Panel
          key={screen.path}
          title={`${screen.n}. ${screen.title}`}
          lead={screen.what}
          action={
            <Link className="btn btn-quiet" to={screen.path}>
              Open {screen.title}
            </Link>
          }
        >
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.1em] text-[var(--muted)]">How to use it</p>
          <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-[var(--ink-soft)]">
            {screen.how.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </Panel>
      ))}

      <Panel title="Safety notes">
        <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-[var(--ink-soft)]">
          <li>SuccessFactors: GET-only for OData metadata and entity feeds. No entity DELETE/POST/PUT/PATCH.</li>
          <li>Approve / Reject changes only the local mapping store used by this app.</li>
          <li>Ingestion and Sync write to Neo4j (or the in-memory graph), not back to SuccessFactors.</li>
          <li>Office Neo4j SSL issues: set NEO4J_TLS_VERIFY=false; at home prefer true.</li>
          <li>Secrets belong in .env or the Connect session — never in chat or committed files.</li>
        </ul>
      </Panel>
    </div>
  );
}
