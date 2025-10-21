# custom_components/microgreens/frontend.py
"""Microgreens cards registration and deploy to /local."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

LOCAL_SUBDIR = "ha-microgreens"
CARDS: tuple[str, ...] = (
    "microgreens-card.js",
    "microgreens-plot-card.js",
)

_VERSION = "1"


def _register_static_path(hass: HomeAssistant, url_path: str, path: str) -> None:
    """Register a static path in a HA-version-compatible way.

    We serve cards directly from the integration package `frontend/` folder instead
    of copying them into `/config/www`.
    """
    try:
        from homeassistant.components.http import StaticPathConfig

        if hasattr(hass.http, "async_register_static_paths"):
            hass.async_create_task(
                hass.http.async_register_static_paths(
                    [StaticPathConfig(url_path, path, True)]
                )
            )
            return
    except Exception:
        pass

    try:
        hass.http.register_static_path(url_path, path, cache_headers=True)
    except Exception:
        _LOGGER.debug("Failed to register static path %s -> %s", url_path, path)


async def _init_resource(hass: HomeAssistant, url: str, ver: str) -> bool:
    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.lovelace.resources import ResourceStorageCollection
    except Exception:
        _LOGGER.debug("Lovelace helpers unavailable; skipping resource init")
        return False

    lovelace = hass.data.get("lovelace")
    if not lovelace:
        _LOGGER.debug("Lovelace storage not available; skipping resource init")
        return False

    resources: ResourceStorageCollection = (
        lovelace.resources if hasattr(lovelace, "resources") else lovelace["resources"]
    )

    await resources.async_get_info()

    url2 = f"{url}?v={ver}"

    for item in resources.async_items():
        if not item.get("url", "").startswith(url):
            continue
        if item["url"].endswith(ver):
            return False
        _LOGGER.debug("Update lovelace resource to: %s", url2)
        if isinstance(resources, ResourceStorageCollection):
            await resources.async_update_item(item["id"], {"res_type": "module", "url": url2})
        else:
            item["url"] = url2
        return True

    if isinstance(resources, ResourceStorageCollection):
        _LOGGER.debug("Add new lovelace resource: %s", url2)
        await resources.async_create_item({"res_type": "module", "url": url2})
    else:
        _LOGGER.debug("Add extra JS module: %s", url2)
        add_extra_js_url(hass, url2)

    return True


async def _migrate_local_resources(
    hass: HomeAssistant, local_prefix: str, new_url: str, ver: str
) -> int:
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection
    except Exception:
        _LOGGER.debug("Lovelace helpers unavailable; skipping local -> integration migration")
        return 0

    lovelace = hass.data.get("lovelace")
    if not lovelace:
        _LOGGER.debug("Lovelace storage not available; skipping migration")
        return 0

    resources: ResourceStorageCollection = (
        lovelace.resources if hasattr(lovelace, "resources") else lovelace["resources"]
    )

    await resources.async_get_info()

    migrated = 0

    for item in list(resources.async_items()):
        u = item.get("url", "")
        if not u.startswith(local_prefix):
            continue

        suffix = u[len(local_prefix) :]
        if not suffix:
            continue

        new_base = new_url.rstrip("/")
        url2 = f"{new_base}/{suffix}?v={ver}"

        _LOGGER.info("Migrating Lovelace resource from %s to %s", u, url2)
        try:
            if isinstance(resources, ResourceStorageCollection):
                await resources.async_update_item(item["id"], {"res_type": "module", "url": url2})
            else:
                item["url"] = url2
            migrated += 1
        except Exception as exc:
            _LOGGER.warning("Failed to migrate resource %s -> %s: %s", u, url2, exc)

    return migrated


class MicrogreensCardRegistration:
    """Serve microgreens cards from the integration package and log instructions."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _src_path(self, name: str) -> Path:
        return Path(__file__).parent / "frontend" / name

    async def async_register(self) -> None:
        card_list = []
        for name in CARDS:
            src = self._src_path(name)
            www_path = Path(__file__).parent / "www" / name
            if www_path.exists():
                serve_path = str(www_path)
            else:
                serve_path = str(src)

            url = f"/{LOCAL_SUBDIR}/{name}"
            _register_static_path(self.hass, url, serve_path)
            card_list.append(url)

        card_list_str = ", ".join(card_list)

        # Attempt delicate auto-registration of the lovelace resource for each card
        for url in card_list:
            try:
                await _init_resource(self.hass, url, _VERSION)
                _LOGGER.debug("Auto-registered lovelace resource for %s", url)
            except Exception:
                _LOGGER.debug("Auto-registration failed for %s", url)

        # Remove old /config/www copies if present
        try:
            for name in CARDS:
                dst = Path(self.hass.config.path("www")) / LOCAL_SUBDIR / name
                if dst.exists():
                    try:
                        dst.unlink()
                        _LOGGER.info("Removed old /config/www copy: %s", dst)
                    except Exception as exc:
                        _LOGGER.debug("Failed to remove old /config/www copy %s: %s", dst, exc)
        except Exception:
            _LOGGER.debug("Could not determine config www path to cleanup old microgreens cards")

        # Migrate any lovelace resources that still point to /local/
        try:
            migrated = await _migrate_local_resources(
                self.hass, f"/local/{LOCAL_SUBDIR}/", f"/{LOCAL_SUBDIR}/", _VERSION
            )
            if migrated:
                _LOGGER.info("Migrated %d Microgreens Lovelace /local/ resources to integration-hosted URLs", migrated)
        except Exception:
            _LOGGER.debug("Local-to-integration resource migration failed for microgreens")

        # Expand any base-only resource entries (e.g. "/ha-microgreens/?v=1")
        try:
            await _expand_base_resource(self.hass, f"/{LOCAL_SUBDIR}/", [
                "microgreens-card.js",
                "microgreens-plot-card.js",
            ])
        except Exception:
            _LOGGER.debug("Failed to expand base resource entries for microgreens")

        _LOGGER.info(
            "Microgreens: cards served from integration at %s; add these as Lovelace resources if needed (type: module)",
            card_list_str,
        )

    async def async_unregister(self) -> None:
        return


async def _expand_base_resource(hass: HomeAssistant, base: str, card_names: list[str]) -> int:
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection
    except Exception:
        _LOGGER.debug("Lovelace helpers unavailable; skipping base resource expansion")
        return 0

    lovelace = hass.data.get("lovelace")
    if not lovelace:
        return 0

    resources: ResourceStorageCollection = (
        lovelace.resources if hasattr(lovelace, "resources") else lovelace["resources"]
    )

    await resources.async_get_info()

    created = 0

    targets = [f"{base.rstrip('/')}/{name}?v={_VERSION}" for name in card_names]

    for item in list(resources.async_items()):
        u = item.get("url", "")
        if not (u == base or u.startswith(base)):
            continue

        suffix = u[len(base) :]
        if suffix and not (suffix.startswith("?") or suffix == ""):
            continue

        _LOGGER.info("Expanding base resource %s into %s", u, ",".join(targets))

        try:
            first = targets[0]
            if isinstance(resources, ResourceStorageCollection):
                await resources.async_update_item(item["id"], {"res_type": "module", "url": first})
            else:
                item["url"] = first
            created += 1

            existing_urls = {it.get("url", "") for it in resources.async_items()}
            for t in targets[1:]:
                if t in existing_urls:
                    continue
                if isinstance(resources, ResourceStorageCollection):
                    await resources.async_create_item({"res_type": "module", "url": t})
                else:
                    resources.async_items().append({"url": t})
                created += 1
        except Exception as exc:
            _LOGGER.warning("Failed to expand base resource %s: %s", u, exc)

    return created
