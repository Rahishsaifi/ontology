"""Write samples/ontology-draft.json from the synthetic metadata. No network calls."""

from pathlib import Path

from app.discovery.parser import parse_edmx
from app.ontology.generator import generate_ontology

ROOT = Path(__file__).resolve().parents[1]
catalog = parse_edmx(
    (ROOT / "samples" / "synthetic-core-hr.edmx").read_bytes(),
    source_system="successfactors",
    generated_at="2024-01-01T00:00:00+00:00",
    origin="synthetic_demo",
)
ontology = generate_ontology(
    catalog,
    [],
    sensitive_patterns=["nationalid", "password", "dateofbirth", "salary"],
)
destination = ROOT / "samples" / "ontology-draft.json"
destination.write_text(ontology.model_dump_json(indent=2), encoding="utf-8")
print(destination)
