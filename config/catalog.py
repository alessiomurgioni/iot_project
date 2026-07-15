import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATES = os.path.join(_BASE, "src", "virtualization", "templates")

PRODUCTS = {
    "dhome": {
        "key": "dhome",
        "label": "DHome — house climate & AC",
        "schema_type": "DHome",
        "schema_path": os.path.join(_TEMPLATES, "DHome.yaml"),
        "services": ["ClimateControlService", "FireNotificationService"],
    },
    # "garage": {
    #     "key": "garage",
    #     "label": "DGarage — door & presence",
    #     "schema_type": "garage",
    #     "schema_path": os.path.join(_TEMPLATES, "DGarage.yaml"),
    #     "services": ["GarageControlService"],
    # },
}

def list_products():
    """
    Retrieve a list of available products.
    """
    return list(PRODUCTS.values())


def get_product(key: str):
    """
    Retrieve a product configuration by its type

    Input:
    - key: the type of the product
    """
    return PRODUCTS.get(key)


def label_for(key: str) -> str:
    """
    Retrieve a label for a product by its type.

    Input:
    - key: the type of the product
    """
    p = PRODUCTS.get(key)
    return p["label"] if p else (key or "Unknown")
