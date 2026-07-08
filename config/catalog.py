import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATES = os.path.join(_BASE, "src", "virtualization", "templates")

PRODUCTS = {
    "dhome": {
        "key": "dhome",
        "label": "DHome — house climate & AC",
        "schema_type": "DHome",
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
