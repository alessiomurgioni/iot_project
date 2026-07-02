from datetime import datetime
from typing import Dict, Any
import uuid

# FIX: was `from schema_registry import SchemaRegistry` — a bare top-level
# import that breaks once this module lives inside a package. Must be
# relative, since schema_registry.py is a sibling in the same directory.
from .schema_registry import SchemaRegistry

_TYPE_MAP = {"str": str, "int": int, "float": (int, float), "bool": bool, "datetime": datetime}


class DRFactory:
    def __init__(self, registry: SchemaRegistry, dr_type: str):
        self.registry = registry
        self.dr_type = dr_type

    def create_dr(self, profile: Dict[str, Any] = None) -> Dict:
        init = self.registry.get_initialization(self.dr_type)
        dr = {
            "_id": str(uuid.uuid4()),
            "type": self.dr_type,
            "profile": profile or {},
            "metadata": {"created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
            "data": dict(init),
        }
        self.validate(dr)
        return dr

    def validate(self, dr: Dict) -> None:
        mandatory = self.registry.get_mandatory_fields(self.dr_type)
        constraints = self.registry.get_type_constraints(self.dr_type)
        data_fields = self.registry.get_data_fields(self.dr_type)
        d = dr.get("data", {})

        for field in mandatory.get("root", []):
            if field not in dr or dr[field] in (None, ""):
                raise ValueError(f"Missing mandatory root field: {field}")
        for field in mandatory.get("metadata", []):
            if field not in dr.get("metadata", {}):
                raise ValueError(f"Missing mandatory metadata field: {field}")

        for field, declared_type in data_fields.items():
            if field not in d or d[field] is None:
                continue
            val = d[field]
            expected = _TYPE_MAP.get(declared_type)
            if expected and not isinstance(val, expected):
                raise ValueError(f"{field}={val!r} is not of type {declared_type}")
            rules = constraints.get(field, {})
            if "enum" in rules and val not in rules["enum"]:
                raise ValueError(f"{field}={val!r} must be one of {rules['enum']}")
            if "min" in rules and val < rules["min"]:
                raise ValueError(f"{field}={val} below min {rules['min']}")
            if "max" in rules and val > rules["max"]:
                raise ValueError(f"{field}={val} above max {rules['max']}")

    def update_dr(self, dr: Dict, updates: Dict[str, Any]) -> Dict:
        dr["data"].update(updates.get("data", {}))
        dr["metadata"]["updated_at"] = datetime.utcnow()
        self.validate(dr)
        return dr
