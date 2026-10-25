"""Candidate Core HR concepts.

Every entry is a guess. Nothing here is an approval.
"""

from __future__ import annotations

import re

CANONICAL_NAMES = frozenset(
    {
        "Person",
        "Employee",
        "Employment",
        "JobAssignment",
        "Department",
        "BusinessUnit",
        "Division",
        "Position",
        "LegalEntity",
        "Manager",
        "UserAccount",
    }
)

REQUIRED_CONCEPTS = [
    "Person",
    "Employee",
    "Employment",
    "JobAssignment",
    "Department",
    "BusinessUnit",
    "Division",
    "Position",
    "LegalEntity",
    "Manager",
]

# Local entity names only. User is intentionally absent: an account is not a person.
PRIMARY_ENTITY_CANDIDATES = {
    "PerPerson": (
        "Person",
        0.62,
        "Inferred from the entity name PerPerson. Confirm that this tenant uses it as the person root.",
    ),
    "EmpEmployment": (
        "Employment",
        0.70,
        "Inferred from the entity name EmpEmployment. This is not an Employee mapping.",
    ),
    "EmpJob": (
        "JobAssignment",
        0.74,
        "Inferred from the entity name EmpJob. Effective-dated rows must stay distinct.",
    ),
    "FODepartment": (
        "Department",
        0.78,
        "Inferred from the foundation-object name FODepartment.",
    ),
    "FOBusinessUnit": (
        "BusinessUnit",
        0.78,
        "Inferred from the foundation-object name FOBusinessUnit.",
    ),
    "FODivision": (
        "Division",
        0.74,
        "Inferred from the foundation-object name FODivision.",
    ),
    "Position": (
        "Position",
        0.70,
        "Inferred from the entity name Position. Confirm the tenant key and effective dating.",
    ),
    "FOCompany": (
        "LegalEntity",
        0.58,
        "Inferred: FOCompany often represents the legal entity. Confirm tenant semantics.",
    ),
}

NAV_SEMANTICS = {
    "manager": (
        "REPORTS_TO",
        0.60,
        "Inferred from the navigation name. Confirm the foreign key before approval.",
    ),
    "department": (
        "BELONGS_TO",
        0.55,
        "Inferred from the navigation name. Confirm the department key.",
    ),
    "businessunit": (
        "BELONGS_TO",
        0.55,
        "Inferred from the navigation name. Confirm the business unit key.",
    ),
    "division": (
        "BELONGS_TO",
        0.50,
        "Inferred from the navigation name. Confirm the division key.",
    ),
    "company": (
        "BELONGS_TO",
        0.45,
        "Inferred from the navigation name. Confirm whether the target is the legal entity.",
    ),
    "position": (
        "OCCUPIES",
        0.55,
        "Inferred from the navigation name. Confirm the position key.",
    ),
    "employment": (
        "HAS_EMPLOYMENT",
        0.50,
        "Inferred from the navigation name. Confirm the employment key.",
    ),
    "person": (
        "RELATED_TO",
        0.35,
        "Inferred from the navigation name. This does not collapse the source into a Person.",
    ),
}

BUSINESS_REL_TYPES = frozenset(
    {
        "REPORTS_TO",
        "BELONGS_TO",
        "OCCUPIES",
        "HAS_EMPLOYMENT",
        "HAS_JOB",
        "ASSIGNED_TO",
        "RELATED_TO",
    }
)

USER_ACCOUNT_NOTE = (
    "A user account is not treated as a Person or an Employment record. "
    "Map it to UserAccount only with an explicit review."
)

EFFECTIVE_START_FIELDS = ("startDate", "effectiveStartDate")
EFFECTIVE_END_FIELDS = ("endDate", "effectiveEndDate")


def normalize_nav_name(name: str) -> str:
    token = re.sub(r"[^a-z0-9]", "", name.lower())
    if token.endswith("nav") and len(token) > 3:
        token = token[:-3]
    return token
