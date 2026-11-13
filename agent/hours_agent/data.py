"""Fake timesheet data. One copy per conversation, kept in memory."""

from copy import deepcopy
from typing import Any

_SEED: dict[str, Any] = {
    "week": "2026-W46",
    "approved": False,
    "entries": [
        {"project": "Contoso migration", "hours": [4, 6, 3.5, 5, 0]},
        {"project": "Fabrikam portal", "hours": [4, 2, 4, 0, 2]},
        {"project": "Internal", "hours": [0, 0, 0.5, 3, 4]},
    ],
    "projects": [
        {
            "project": "Contoso migration",
            "client": "Contoso",
            "hoursUsed": 64.5,
            "budgetHours": 120,
        },
        {
            "project": "Fabrikam portal",
            "client": "Fabrikam",
            "hoursUsed": 36,
            "budgetHours": 40,
        },
        {
            "project": "Northwind audit",
            "client": "Northwind",
            "hoursUsed": 52,
            "budgetHours": 45,
        },
    ],
}


def new_timesheet() -> dict[str, Any]:
  return deepcopy(_SEED)
