"""Synthetic Core HR records. Names and identifiers are fictional."""

from __future__ import annotations

DEMO_BASE_URL = "https://demo.successfactors.local/odata/v2"

_MODIFIED = "2024-01-15T00:00:00"
_LATER = "2024-06-01T00:00:00"


def demo_records() -> dict[str, list[dict]]:
    return {
        "User": [
            {
                "userId": "U001",
                "displayName": "Avery Example",
                "email": "avery.example@example.com",
                "status": "active",
                "managerId": None,
                "password": None,
                "nationalId": None,
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "userId": "U002",
                "displayName": "Blake Example",
                "email": "blake.example@example.com",
                "status": "active",
                "managerId": "U001",
                "password": None,
                "nationalId": None,
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "userId": "U003",
                "displayName": "Casey Example",
                "email": "casey.example@example.com",
                "status": "active",
                "managerId": "U002",
                "password": None,
                "nationalId": None,
                "lastModifiedDateTime": _LATER,
            },
        ],
        "PerPerson": [
            {"personIdExternal": "P001", "dateOfBirth": None, "lastModifiedDateTime": _MODIFIED},
            {"personIdExternal": "P002", "dateOfBirth": None, "lastModifiedDateTime": _MODIFIED},
            {"personIdExternal": "P003", "dateOfBirth": None, "lastModifiedDateTime": _LATER},
        ],
        "PerPersonal": [
            {
                "personIdExternal": "P001",
                "startDate": "2019-01-01T00:00:00",
                "endDate": None,
                "firstName": "Avery",
                "lastName": "Example",
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "personIdExternal": "P002",
                "startDate": "2020-01-01T00:00:00",
                "endDate": None,
                "firstName": "Blake",
                "lastName": "Example",
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "personIdExternal": "P003",
                "startDate": "2021-03-01T00:00:00",
                "endDate": None,
                "firstName": "Casey",
                "lastName": "Example",
                "lastModifiedDateTime": _LATER,
            },
        ],
        "EmpEmployment": [
            {
                "userId": "U001",
                "personIdExternal": "P001",
                "startDate": "2019-01-01T00:00:00",
                "endDate": None,
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "userId": "U002",
                "personIdExternal": "P002",
                "startDate": "2020-01-01T00:00:00",
                "endDate": None,
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "userId": "U003",
                "personIdExternal": "P003",
                "startDate": "2021-03-01T00:00:00",
                "endDate": None,
                "lastModifiedDateTime": _LATER,
            },
        ],
        "EmpJob": [
            {
                "userId": "U001",
                "startDate": "2019-01-01T00:00:00",
                "endDate": None,
                "seqNumber": 1,
                "fte": "1.0",
                "jobTitle": "Engineer",
                "department": "DEPT-ENG",
                "position": "POS-ENG",
                "businessUnit": "BU-PRODUCT",
                "division": "DIV-CORP",
                "company": "LE-EXAMPLE",
                "managerId": None,
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "userId": "U002",
                "startDate": "2020-01-01T00:00:00",
                "endDate": "2022-05-31T00:00:00",
                "seqNumber": 1,
                "fte": "1.0",
                "jobTitle": "Engineer",
                "department": "DEPT-ENG",
                "position": "POS-ENG",
                "businessUnit": "BU-PRODUCT",
                "division": "DIV-CORP",
                "company": "LE-EXAMPLE",
                "managerId": "U001",
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "userId": "U002",
                "startDate": "2022-06-01T00:00:00",
                "endDate": None,
                "seqNumber": 2,
                "fte": "1.0",
                "jobTitle": "HR Specialist",
                "department": "DEPT-HR",
                "position": "POS-HR",
                "businessUnit": "BU-PRODUCT",
                "division": "DIV-CORP",
                "company": "LE-EXAMPLE",
                "managerId": "U001",
                "lastModifiedDateTime": _LATER,
            },
            {
                "userId": "U003",
                "startDate": "2021-03-01T00:00:00",
                "endDate": None,
                "seqNumber": 1,
                "fte": "1.0",
                "jobTitle": "Engineer",
                "department": "DEPT-ENG",
                "position": "POS-ENG",
                "businessUnit": "BU-PRODUCT",
                "division": "DIV-CORP",
                "company": "LE-EXAMPLE",
                "managerId": "U002",
                "lastModifiedDateTime": _LATER,
            },
        ],
        "FODepartment": [
            {
                "externalCode": "DEPT-ENG",
                "name": "Engineering",
                "description": "Synthetic engineering department",
                "status": "active",
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "externalCode": "DEPT-HR",
                "name": "People Operations",
                "description": "Synthetic people department",
                "status": "active",
                "lastModifiedDateTime": _MODIFIED,
            },
        ],
        "FOBusinessUnit": [
            {
                "externalCode": "BU-PRODUCT",
                "name": "Product",
                "status": "active",
                "lastModifiedDateTime": _MODIFIED,
            }
        ],
        "FODivision": [
            {
                "externalCode": "DIV-CORP",
                "name": "Corporate",
                "status": "active",
                "lastModifiedDateTime": _MODIFIED,
            }
        ],
        "Position": [
            {
                "code": "POS-ENG",
                "externalName": "Engineer",
                "vacant": False,
                "lastModifiedDateTime": _MODIFIED,
            },
            {
                "code": "POS-HR",
                "externalName": "HR Specialist",
                "vacant": False,
                "lastModifiedDateTime": _MODIFIED,
            },
        ],
        "FOCompany": [
            {
                "externalCode": "LE-EXAMPLE",
                "name": "Example Legal Entity",
                "status": "active",
                "lastModifiedDateTime": _MODIFIED,
            }
        ],
        "UnkeyedCustom": [{"label": "This row has no key and must be rejected."}],
        "VendorNote": [
            {
                "noteId": "NOTE-1",
                "comment": "Synthetic vendor note",
                "size": 12,
                "lastModifiedDateTime": _MODIFIED,
            }
        ],
    }
