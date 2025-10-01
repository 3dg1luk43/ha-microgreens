# custom_components/microgreens/frontend.py
"""Microgreens cards registration and deploy to /local."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Iterable

from homeassistant.components.lovelace import LovelaceData
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

LOCAL_SUBDIR = "ha-microgreens"  # -> /config/www/ha-microgreens
CARDS: tuple[str, ...] = (
    "microgreens-card.js",
    "microgreens-plot-card.js",
)

def _local_url(name: str) -> str:
    return f"/local/{LOCAL_SUBDIR}/{name}"


class MicrogreensCardRegistration:
    """Deploy cards into /config/www and register Lovelace resources in storage mode."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _src_path(self, name: str) -> Path:
        # cards are bundled inside the integration package
        return Path(__file__).parent / "frontend" / name

    def _dst_path(self, name: str) -> Path:
        # /config/www/ha-microgreens/<name>
        return Path(self.hass.config.path("www")) / LOCAL_SUBDIR / name

    async def _deploy_cards(self) -> None:
        """Copy cards if missing or outdated (mtime-based)."""
        for name in CARDS:
            src = self._src_path(name)
            dst = self._dst_path(name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                need_copy = (not dst.exists()) or (
                    src.stat().st_mtime_ns > dst.stat().st_mtime_ns
                )
                if need_copy:
                    shutil.copy2(src, dst)
                    _LOGGER.info("Microgreens: deployed card to %s", dst)
                else:
                    _LOGGER.debug("Microgreens: card up-to-date at %s", dst)
            except Exception as exc:
                _LOGGER.warning("Microgreens: failed to deploy %s to %s: %s", name, dst, exc)

    async def async_register(self) -> None:
        """Deploy cards and ensure Lovelace resources exist (storage mode only)."""
        await self._deploy_cards()

        lovelace: LovelaceData | None = self.hass.data.get("lovelace")
        if lovelace is None or lovelace.mode != "storage":
            # YAML mode => user manages resources in configuration.yaml
            _LOGGER.debug("Lovelace not in storage mode; skipping resource auto-register")
            return

        # create resources if missing
        existing = lovelace.resources.async_items()
        have_urls = {r.get("url") for r in existing}
        needed: Iterable[str] = (_local_url(n) for n in CARDS)

        for url in needed:
            if url not in have_urls:
                _LOGGER.info("Microgreens: registering Lovelace resource: %s", url)
                await lovelace.resources.async_create_item(
                    {"res_type": "module", "url": url}
                )
            else:
                _LOGGER.debug("Microgreens: Lovelace resource already present: %s", url)

    async def async_unregister(self) -> None:
        """Remove Lovelace resources (keep files in /config/www)."""
        lovelace: LovelaceData | None = self.hass.data.get("lovelace")
        if lovelace is None or lovelace.mode != "storage":
            return

        # delete both resources if present
        to_delete = []
        for r in lovelace.resources.async_items():
            if r.get("url") in {_local_url(n) for n in CARDS}:
                rid = r.get("id")
                if rid:
                    to_delete.append(rid)

        for rid in to_delete:
            try:
                _LOGGER.info("Microgreens: removing Lovelace resource id=%s", rid)
                await lovelace.resources.async_delete_item(rid)
            except Exception as exc:
                _LOGGER.warning("Microgreens: failed removing resource id=%s: %s", rid, exc)
