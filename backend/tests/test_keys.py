import pytest

from app.errors import MissingKeyError
from app.mapping.keys import build_source_key, composite_identity, split_pairs


def test_composite_key_is_deterministic_and_order_follows_metadata():
    record = {"startDate": "2020-01-01T00:00:00", "userId": "U002", "extra": "ignore"}
    types = {"userId": "Edm.String", "startDate": "Edm.DateTime"}
    first = build_source_key(["userId", "startDate"], record, types)
    second = build_source_key(["userId", "startDate"], dict(reversed(list(record.items()))), types)
    assert first == second == "userId=U002|startDate=2020-01-01T00:00:00"
    assert split_pairs(first) == [("userId", "U002"), ("startDate", "2020-01-01T00:00:00")]


def test_key_escapes_delimiters_and_round_trips():
    record = {"userId": "a|b=c\\d"}
    key = build_source_key(["userId"], record, {"userId": "Edm.String"})
    assert split_pairs(key) == [("userId", "a|b=c\\d")]


def test_missing_and_empty_keys_are_rejected():
    with pytest.raises(MissingKeyError):
        build_source_key(["userId"], {}, {"userId": "Edm.String"})
    with pytest.raises(MissingKeyError):
        build_source_key(["userId"], {"userId": "  "}, {"userId": "Edm.String"})
    with pytest.raises(MissingKeyError):
        build_source_key([], {"userId": "U001"}, {})


def test_string_keys_keep_leading_zeros_and_datetimes_canonicalize():
    assert build_source_key(["userId"], {"userId": "001"}, {"userId": "Edm.String"}) == "userId=001"
    assert (
        build_source_key(["startDate"], {"startDate": "2020-01-01T00:00:00Z"}, {"startDate": "Edm.DateTime"})
        == "startDate=2020-01-01T00:00:00"
    )
    assert (
        build_source_key(["startDate"], {"startDate": "/Date(1577836800000)/"}, {"startDate": "Edm.DateTime"})
        == "startDate=2020-01-01T00:00:00"
    )


def test_identity_changes_when_any_component_changes():
    left = composite_identity("successfactors", "SFOData.EmpJob", "userId=U002|startDate=2020-01-01T00:00:00")
    right = composite_identity("successfactors", "SFOData.EmpJob", "userId=U002|startDate=2022-06-01T00:00:00")
    assert left != right
