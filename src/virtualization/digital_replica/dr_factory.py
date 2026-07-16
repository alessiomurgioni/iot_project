from datetime import datetime
from pydantic import create_model, Field, field_validator
import yaml
import uuid


class DRFactory:
    def __init__(self, schema_path: str):
        self.schema = self._load_schema(schema_path)
        if not self.schema or "schemas" not in self.schema:
            raise ValueError(f"Invalid schema structure in {schema_path}")

    def _load_schema(self, path: str) -> dict:
        """
        Read the YAML schema file.

        Inputs:
        - path: path to the YAML schema file

        Outputs:
        - parsed schema dict
        """
        try:
            with open(path, "r") as file:
                return yaml.safe_load(file)
        except Exception as e:
            raise ValueError(f"Failed to load schema: {str(e)}")

    def _create_profile_model(self):
        mandatory_fields = (
            self.schema["schemas"].get("validations", {})
            .get("mandatory_fields", {}).get("profile", [])
        )
        type_constraints = self.schema["schemas"].get("validations", {}).get("type_constraints", {})

        field_definitions = {}
        profile_fields = self.schema["schemas"]["common_fields"].get("profile", {})
        for field_name, field_type in profile_fields.items():
            is_required = field_name in mandatory_fields
            constraints = {}
            if field_name in type_constraints:
                rules = type_constraints[field_name]
                if "min" in rules:
                    constraints["ge"] = rules["min"]
                if "max" in rules:
                    constraints["le"] = rules["max"]
            field_definitions[field_name] = (
                (str if field_type == "str" else
                 int if field_type == "int" else
                 float if field_type == "float" else
                 datetime if field_type == "datetime" else object),
                Field(None if not is_required else ..., **constraints),
            )
        model = create_model("Profile", **field_definitions)

        for field_name in field_definitions:
            if field_name in type_constraints and "enum" in type_constraints[field_name]:
                enum_values = type_constraints[field_name]["enum"]

                @field_validator(field_name)
                def validate_enum(value, field):
                    if value not in enum_values:
                        raise ValueError(f"{field.name} must be one of {enum_values}")
                    return value

                setattr(model, f"validate_{field_name}", validate_enum)
        return model

    def _create_data_model(self):
        type_constraints = self.schema["schemas"].get("validations", {}).get("type_constraints", {})
        data_fields = self.schema["schemas"].get("entity", {}).get("data", {})

        field_definitions = {}
        for field_name, field_type in data_fields.items():
            if field_type == "List[Dict]":
                field_definitions[field_name] = (list[dict], Field(default_factory=list))
            elif field_type == "List[str]":
                field_definitions[field_name] = (list[str], Field(default_factory=list))
            else:
                field_definitions[field_name] = (
                    (str if field_type == "str" else
                     int if field_type == "int" else
                     float if field_type == "float" else object),
                    Field(None),
                )
        model = create_model("Data", **field_definitions)

        for field_name, field_type in data_fields.items():
            if field_name in type_constraints and "enum" in type_constraints[field_name]:
                enum_values = type_constraints[field_name]["enum"]

                @field_validator(field_name)
                def validate_enum(value, field):
                    if value not in enum_values:
                        raise ValueError(f"{field.name} must be one of {enum_values}")
                    return value

                setattr(model, f"validate_{field_name}", validate_enum)
        return model

    def create_dr(self, dr_type: str, initial_data: dict) -> dict:
        """
        Build a new, Digital Replica document.

        Inputs:
        - dr_type: the replica's schema type
        - initial_data: optional initial "profile"/"data"/"metadata" values

        Outputs:
        - a new Digital Replica document
        """
        ProfileModel = self._create_profile_model()
        DataModel = self._create_data_model()

        dr_dict = {
            "_id": str(uuid.uuid4()),
            "type": dr_type,
            "metadata": {"created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
            "data": {},
        }

        init_values = self.schema["schemas"].get("validations", {}).get("initialization", {})
        for section, defaults in init_values.items():
            if section == "metadata":
                dr_dict["metadata"].update(defaults)
            elif section in ["status", "sensors", "devices", "medications", "measurements"]:
                dr_dict["data"][section] = defaults
            else:
                dr_dict[section] = defaults

        if "profile" in initial_data:
            profile = ProfileModel(**initial_data["profile"])
            dr_dict["profile"] = profile.model_dump(exclude_unset=True)
        if "data" in initial_data:
            data = DataModel(**{**dr_dict["data"], **initial_data["data"]})
            dr_dict["data"] = data.model_dump(exclude_unset=True)
        if "metadata" in initial_data:
            dr_dict["metadata"].update(initial_data["metadata"])

        return dr_dict

    def update_dr(self, dr: dict, updates: dict) -> dict:
        """
        Update the given Digital Replica document with the given updates.

        Inputs:
        - dr: the current Digital Replica document
        - updates: values to update inside the Digital Replica document
        """
        ProfileModel = self._create_profile_model()
        DataModel = self._create_data_model()
        updated_dr = dr.copy()

        if "profile" in updates:
            current_profile = updated_dr.get("profile", {})
            profile = ProfileModel(**(current_profile | updates["profile"]))
            updated_dr["profile"] = profile.model_dump(exclude_unset=True)
        if "data" in updates:
            current_data = updated_dr.get("data", {})
            data = DataModel(**(current_data | updates["data"]))
            updated_dr["data"] = data.model_dump(exclude_unset=True)
        if "metadata" in updates:
            updated_dr["metadata"].update(updates["metadata"])

        updated_dr["metadata"]["updated_at"] = datetime.utcnow()
        return updated_dr
