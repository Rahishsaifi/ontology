import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "./api";
import { Banner } from "./components";
import { ConnectPage } from "./pages/Connect";
import { DocsPage } from "./pages/Docs";
import { GraphPage } from "./pages/Graph";
import { IngestionPage } from "./pages/Ingestion";
import { OntologyPage } from "./pages/Ontology";
import { OverviewPage } from "./pages/Overview";
import { QueryPage } from "./pages/Query";
import { SchemaPage } from "./pages/Schema";
import { SyncPage } from "./pages/Sync";

const links = [
  ["/", "Overview"],
  ["/connect", "Connect"],
  ["/schema", "Schema"],
  ["/ontology", "Ontology"],
  ["/query", "Query"],
  ["/sync", "Sync"],
  ["/ingestion", "Ingestion"],
  ["/graph", "Graph"],
  ["/docs", "Docs"],
];

export function App() {
  const [demo, setDemo] = useState<boolean | null>(null);
  const location = useLocation();

  useEffect(() => {
    api<{ demo_mode: boolean }>("/api/health")
      .then((health) => setDemo(health.demo_mode))
      .catch(() => setDemo(null));
  }, []);

  return (
    <div className="app-shell grid min-h-screen grid-cols-1 lg:grid-cols-[15.5rem_minmax(0,1fr)]">
      <aside className="nav-rail lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto">
        <div className="flex items-center justify-between gap-4 px-4 py-3 lg:block lg:px-5 lg:pb-4 lg:pt-6">
          <div>
            <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-teal-200/80">SuccessFactors</p>
            <p className="brand-mark text-[1.55rem] leading-none text-white lg:mt-1 lg:text-[1.85rem]">Ontology</p>
            <p className="mt-1 hidden text-xs leading-relaxed text-white/55 lg:block">
              Core HR model review and knowledge graph
            </p>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto border-t border-white/10 px-2 py-2 lg:block lg:space-y-0.5 lg:overflow-visible lg:border-t-0 lg:px-0 lg:pb-6">
          {links.map(([path, label]) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) =>
                `nav-link whitespace-nowrap lg:whitespace-normal ${isActive ? "nav-link-active" : ""}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-col bg-transparent">
        {demo ? (
          <Banner text="Demo mode is on. Tenant data is synthetic and no SuccessFactors call is made." />
        ) : null}
        <main key={location.pathname} className="page-enter flex-1 space-y-4 p-4 lg:p-7">
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/connect" element={<ConnectPage />} />
            <Route path="/schema" element={<SchemaPage />} />
            <Route path="/ontology" element={<OntologyPage />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/ingestion" element={<IngestionPage />} />
            <Route path="/query" element={<QueryPage />} />
            <Route path="/sync" element={<SyncPage />} />
            <Route path="/docs" element={<DocsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
