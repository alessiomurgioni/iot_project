import os

"""
Fixed catalog of device *types* (products) the platform supports. A product is
the single source of truth binding a user-facing device type to the Digital
Twin machinery it needs:

- schema_type / schema_path : the Digital Replica schema for this product
  (routed by SchemaRegistry / DRFactory, one Mongo collection per schema_type).
- services                  : the services attached to every twin of this type.
- dashboard_template        : the page rendered when opening one of its devices.

The set is intentionally fixed — adding a product is a single entry here (plus
its schema YAML and, if new, its services). For now the only product is DHome
(house climate + AC). The add-device dropdown is populated from list_products(),
and the claim flow validates the chosen product against get_product().
"""

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATES = os.path.join(_BASE, "src", "virtualization", "templates")

PRODUCTS = {
    "dhome": {
        "key": "dhome",
        "label": "DHome — house climate & AC",
        "schema_type": "house",
        "schema_path": os.path.join(_TEMPLATES, "DHome.yaml"),
        "services": ["ClimateControlService", "MonitoringService", "FireNotificationService"],
        "dashboard_template": "DHome/dashboard.html",
    },
    # To add a product later, e.g.:
    # "garage": {
    #     "key": "garage",
    #     "label": "DGarage — door & presence",
    #     "schema_type": "garage",
    #     "schema_path": os.path.join(_TEMPLATES, "DGarage.yaml"),
    #     "services": ["DoorControlService", "MonitoringService"],
    #     "dashboard_template": "garage_dashboard.html",
    # },
}

DEFAULT_PRODUCT = "dhome"


def list_products():
    """All products, for the add-device dropdown (stable order)."""
    return list(PRODUCTS.values())


def get_product(key: str):
    """A product by key, or None if the key isn't in the fixed catalog."""
    return PRODUCTS.get(key)


def label_for(key: str) -> str:
    """Display label for a product key (falls back to the raw key)."""
    p = PRODUCTS.get(key)
    return p["label"] if p else (key or "Unknown")
