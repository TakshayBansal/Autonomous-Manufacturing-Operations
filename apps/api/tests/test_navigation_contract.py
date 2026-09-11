from app.core.permissions import ADMIN, PURCHASE_MANAGER
from app.domains.workflows import NAV_ITEMS, ROLE_NAV_KEYS


def test_external_delivery_is_visible_to_authorized_roles() -> None:
    assert NAV_ITEMS["outbox"].href == "/outbox"
    assert "outbox" in ROLE_NAV_KEYS[PURCHASE_MANAGER]
    assert "outbox" in ROLE_NAV_KEYS[ADMIN]
