"""Metadata discovery."""

from app.discovery.parser import catalog_hash, parse_edmx

parse_metadata = parse_edmx
catalog_content_hash = catalog_hash

__all__ = ["catalog_content_hash", "catalog_hash", "parse_edmx", "parse_metadata"]
