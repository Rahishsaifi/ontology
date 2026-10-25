# SuccessFactors Ontology and Knowledge Graph Builder

Discover a Core HR schema, review an ontology, and load the approved model into a graph. The application does not assume every SuccessFactors entity is enabled. It reads the entity sets, types, keys, and associations that the metadata actually contains.

## Demo and live mode

Demo mode is the default in `.env.example`. It reads `samples/synthetic-core-hr.edmx` and fictional people (Avery, Blake, and Casey Example). It does not open a network connection to SAP.

Live mode requires `DEMO_MODE=false` and your own tenant URL plus one configured auth method: `oauth_bearer`, `basic`, or `oauth_saml_bearer`. The SAML option exchanges an assertion you already have. This app does not mint SAML assertions. A live connection and a live graph import have not been executed in this repository.

## Setup (no Docker)

Python 3.12+ and Node 22+ are required. This workspace was tested with Python 3.14.

```bash
cp .env.example .env
chmod +x scripts/run-local.sh
./scripts/run-local.sh
```

That script creates `.venv` if needed, installs Python and frontend deps when missing, then starts the API and UI together. Stop with Ctrl+C.

Or use Make:

```bash
make run
```

Open http://127.0.0.1:5173. With both API tokens empty and `DEMO_MODE=true`, use `demo-admin` or `demo-reader`. API docs: http://127.0.0.1:8000/docs.

To start the processes separately:

```bash
make install
make api    # terminal 1
make ui     # terminal 2
```

```bash
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```

## Docker Compose

Compose starts Neo4j Community 5.26, the API, and the Vite dev server. The compose password `local-dev-only` is for this local stack only. The API tokens in compose are `local-admin-token` and `local-reader-token`.

```bash
docker compose up --build
```

Set `NEO4J_INTEGRATION=1` to run the optional Neo4j test against a database you started yourself. That test is skipped unless the variable is set, and it was not run here.

## Architecture

- `backend/app/connector` authenticates, downloads metadata, and pages OData. The HTTP client is GET-only for SuccessFactors. Next links must stay on the same scheme, host, port, and base path.
- `backend/app/discovery` parses EDMX locally. External `edmx:Reference` URLs are recorded and never fetched. XML entities and DTDs are rejected.
- `backend/app/ontology` proposes canonical Core HR concepts. User is not inferred as Person, Employee, or Employment. Guesses stay `review_required` until a person approves them.
- `backend/app/sync` upserts approved entities. Relationship edges are reconciled only after a non-empty successful full sync. A failed or empty read keeps the existing graph.
- `backend/app/graph` writes to memory or Neo4j. Neo4j Community cannot enforce a multi-property node key, so uniqueness is a single `identity` property built from source system, entity type, and source key.
- The React dashboard talks only to this API. It keeps the API bearer token in `sessionStorage`.

## Security

Secrets belong in the environment or in the API process for the current session (`DELETE /api/connections/successfactors/session` clears them). They are not written into SQLite, ontology JSON, or the frontend bundle. Logs redact bearer tokens, basic credentials, and common secret field names. Cypher from the query screen must be one read-only statement. Dynamic labels are not taken from metadata. TLS verification is on unless `TLS_VERIFY=false` is set explicitly.

## Sample files

- `samples/synthetic-core-hr.edmx` — synthetic Core HR metadata, including an unresolved navigation and an external reference that must be ignored.
- `samples/ontology-draft.json` — generated draft. Nothing in it is approved.
- `samples/reviewed-mappings.json` — explicit approvals and rejections for the synthetic tenant.
- `samples/graph-queries.json` — saved read-only queries.

Regenerate the draft with `PYTHONPATH=backend .venv/bin/python scripts/export_sample_ontology.py`.

## Dashboard

Overview, Connect, Schema, Ontology, Graph, Ingestion, Query, and Sync are the eight screens. A typical demo path is: enter `demo-admin`, discover metadata, generate the draft, import the sample review, dry-run EmpJob, then import the Core HR sets and run the reporting-lines query.

## Limitations

- No live SuccessFactors tenant was connected, and no live import was verified.
- The memory graph answers the saved query library. Arbitrary Cypher needs Neo4j and still has to pass the read-only guard.
- Full sync does not delete nodes that disappeared from the feed. Relationship reconciliation removes edges for that mapping only after a complete non-empty full sync. Aged node deletion is a separate admin action.
- Effective-dated entities whose date is not part of the key are blocked until a reviewer chooses `preserve_history` or `current_snapshot`.
- The optional Neo4j integration test was not executed.
# ontology
