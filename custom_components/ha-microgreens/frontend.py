# custom_components/microgreens/frontend.py
"""Microgreens cards registration and deploy to /local."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
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
    """Deploy cards into /config/www without touching Lovelace resources."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _src_path(self, name: str) -> Path:
        # cards are bundled inside the integration package
        return Path(__file__).parent / "frontend" / name

    def _dst_path(self, name: str) -> Path:
        # /config/www/ha-microgreens/<name>
        return Path(self.hass.config.path("www")) / LOCAL_SUBDIR / name

    def _copy_if_needed(self, src: Path, dst: Path) -> None:
        """Synchronous helper: mkdir, compare mtimes, and copy if newer/missing."""
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
            _LOGGER.warning("Microgreens: failed to deploy %s to %s: %s", src.name, dst, exc)

    async def _deploy_cards(self) -> None:
        """Copy cards if missing or outdated (mtime-based)."""
        for name in CARDS:
            src = self._src_path(name)
            dst = self._dst_path(name)
            # Run blocking I/O in executor to avoid blocking the event loop
            await self.hass.async_add_executor_job(self._copy_if_needed, src, dst)

    async def async_register(self) -> None:
        """Deploy cards and log manual instructions for Lovelace resources."""
        await self._deploy_cards()
        card_list = ", ".join(_local_url(name) for name in CARDS)
        _LOGGER.info(
            "Microgreens: cards deployed under /config/www; add Lovelace resources manually if needed: %s (type: module)",
            card_list,
        )

    async def async_unregister(self) -> None:
        """No-op; leave Lovelace resources untouched."""
        return
