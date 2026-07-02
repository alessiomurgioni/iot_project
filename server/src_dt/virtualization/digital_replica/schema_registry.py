from typing import Dict
import yaml


class SchemaRegistry:
    def __init__(self):
        self.schemas: Dict[str, Dict] = {}

    def load_schema(self, schema_type: str, yaml_path: str) -> None:
        with open(yaml_path, "r") as f:
            raw = yaml.safe_load(f)
        if not raw or "schemas" not in raw:
            raise ValueError(f"Invalid schema structure in {yaml_path}")
        self.schemas[schema_type] = raw["schemas"]

    def get_schema(self, schema_type: str) -> Dict:
        if schema_type not in self.schemas:
            raise ValueError(f"Schema not found for type: {schema_type}")
        return self.schemas[schema_type]

    def get_data_fields(self, schema_type: str) -> Dict:
        return self.get_schema(schema_type).get("entity", {}).get("data", {})

    def get_type_constraints(self, schema_type: str) -> Dict:
        return self.get_schema(schema_type).get("validations", {}).get("type_constraints", {})

    def get_mandatory_fields(self, schema_type: str) -> Dict:
        return self.get_schema(schema_type).get("validations", {}).get("mandatory_fields", {})

    def get_initialization(self, schema_type: str) -> Dict:
        return self.get_schema(schema_type).get("validations", {}).get("initialization", {})

    def get_collection_name(self, schema_type: str) -> str:
        return f"{schema_type}_collection"
