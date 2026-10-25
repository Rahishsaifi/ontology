"""JSON documents for the catalog, ontology, and reviews."""

from __future__ import annotations

from app.config import Settings
from app.errors import NotFoundError
from app.models.catalog import SchemaCatalog
from app.models.ontology import OntologyDocument, ReviewFile


def _path(settings: Settings, name: str):
    return settings.data_path() / name


def _write(path, model) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)


def save_catalog(settings: Settings, catalog: SchemaCatalog) -> None:
    _write(_path(settings, "catalog.json"), catalog)


def load_catalog(settings: Settings) -> SchemaCatalog:
    path = _path(settings, "catalog.json")
    if not path.exists():
        raise NotFoundError("Metadata has not been discovered yet.", code="catalog_not_found")
    return SchemaCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def save_ontology(settings: Settings, ontology: OntologyDocument) -> None:
    _write(_path(settings, "ontology.json"), ontology)


def load_ontology(settings: Settings) -> OntologyDocument:
    path = _path(settings, "ontology.json")
    if not path.exists():
        raise NotFoundError("An ontology draft has not been generated yet.", code="ontology_not_found")
    return OntologyDocument.model_validate_json(path.read_text(encoding="utf-8"))


def load_reviews(settings: Settings) -> ReviewFile:
    path = _path(settings, "reviews.json")
    if not path.exists():
        return ReviewFile(source_system=settings.source_system, mappings=[])
    return ReviewFile.model_validate_json(path.read_text(encoding="utf-8"))


def save_reviews(settings: Settings, reviews: ReviewFile) -> None:
    _write(_path(settings, "reviews.json"), reviews)
