#!/usr/bin/env python3
# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Driver for the Microgreens test box (http://127.0.0.1:8324).

    ./hactl.py wait [--timeout 240]       wait for HTTP (and the integration, once set up)
    ./hactl.py onboard                    owner user + long-lived token in config/.testbox_token
    ./hactl.py setup                      add Microgreens through the real config flow
    ./hactl.py ws ha_microgreens/snapshot [key=value ...]
    ./hactl.py call ha_microgreens.sow plot=A1 crop=radish
    ./hactl.py state sensor.plot_a1_status
    ./hactl.py notifications              payloads the capture notify platform received
    ./hactl.py errors                     ERROR / WARNING lines about the integration
    ./hactl.py restart                    restart the container (reloads the mounted code)

Values in key=value are parsed as JSON when they can be (`plot_ids='["A1"]'`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import aiohttp

HERE = Path(__file__).resolve().parent
CONFIG_DIR = HERE / "config"
TOKEN_FILE = CONFIG_DIR / ".testbox_token"
CAPTURE_FILE = CONFIG_DIR / "notify_capture.jsonl"
LOG_FILE = CONFIG_DIR / "home-assistant.log"
BASE_URL = os.environ.get("TESTBOX_URL", "http://127.0.0.1:8324")
CLIENT_ID = f"{BASE_URL}/"
DOMAIN = "ha_microgreens"
OWNER = {"name": "Test Box", "username": "testbox", "password": "testbox-pw-0123"}


def token() -> str:
    if not TOKEN_FILE.exists():
        sys.exit(f"no token at {TOKEN_FILE}; run ./hactl.py onboard first")
    return TOKEN_FILE.read_text().strip()


def _kv(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        try:
            out[key] = json.loads(raw)
        except ValueError:
            out[key] = raw
    return out


async def rest(session: aiohttp.ClientSession, method: str, path: str, payload: Any = None, auth: bool = True) -> Any:
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {token()}"
    async with session.request(method, f"{BASE_URL}{path}", headers=headers, json=payload) as resp:
        body = await resp.text()
        if resp.status >= 400:
            raise RuntimeError(f"{method} {path} -> {resp.status}: {body[:400]}")
        return json.loads(body) if body.strip() else None


class WS:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._id = 0

    async def __aenter__(self) -> WS:
        self._ws = await self._session.ws_connect(f"{BASE_URL}/api/websocket")
        await self._ws.receive_json()
        await self._ws.send_json({"type": "auth", "access_token": token()})
        if (await self._ws.receive_json())["type"] != "auth_ok":
            raise RuntimeError("websocket auth failed")
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._ws is not None:
            await self._ws.close()

    async def cmd(self, type_: str, **fields: Any) -> Any:
        assert self._ws is not None
        self._id += 1
        await self._ws.send_json({"id": self._id, "type": type_, **fields})
        while True:
            msg = await self._ws.receive_json()
            if msg.get("id") == self._id and msg.get("type") == "result":
                if not msg["success"]:
                    raise RuntimeError(f"{type_}: {msg['error']}")
                return msg.get("result")


async def cmd_onboard(_args: argparse.Namespace) -> int:
    async with aiohttp.ClientSession() as session:
        if TOKEN_FILE.exists():
            try:
                await rest(session, "GET", "/api/")
                print("already onboarded")
                return 0
            except RuntimeError:
                pass
        step = await rest(
            session,
            "POST",
            "/api/onboarding/users",
            {"client_id": CLIENT_ID, "language": "en", **OWNER},
            auth=False,
        )
        async with session.post(
            f"{BASE_URL}/auth/token",
            data={"grant_type": "authorization_code", "code": step["auth_code"], "client_id": CLIENT_ID},
        ) as resp:
            tokens = await resp.json()
        TOKEN_FILE.write_text(tokens["access_token"])
        async with WS(session) as ws:
            long_lived = await ws.cmd(
                "auth/long_lived_access_token", client_name=f"testbox-{uuid.uuid4().hex[:8]}", lifespan=365
            )
        TOKEN_FILE.write_text(long_lived)
        TOKEN_FILE.chmod(0o600)
        # The rest of onboarding, or the UI redirects to onboarding.html.
        for path, body in (
            ("/api/onboarding/core_config", {}),
            ("/api/onboarding/analytics", {}),
            ("/api/onboarding/integration", {"client_id": CLIENT_ID, "redirect_uri": f"{BASE_URL}/?auth_callback=1"}),
        ):
            try:
                await rest(session, "POST", path, body)
            except RuntimeError:
                pass
    print(f"onboarded; UI {BASE_URL} user {OWNER['username']} password {OWNER['password']}")
    return 0


async def cmd_wait(args: argparse.Namespace) -> int:
    deadline = time.monotonic() + args.timeout
    async with aiohttp.ClientSession() as session:
        while time.monotonic() < deadline:
            try:
                async with session.get(f"{BASE_URL}/manifest.json") as resp:
                    if resp.status == 200:
                        break
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(2)
        else:
            print("timed out waiting for the box", file=sys.stderr)
            return 1
        if not TOKEN_FILE.exists():
            print("box is up (not onboarded)")
            return 0
        entries = await rest(session, "GET", f"/api/config/config_entries/entry?domain={DOMAIN}")
        if not entries:
            print("box is up (Microgreens not set up)")
            return 0
        while time.monotonic() < deadline:
            try:
                async with WS(session) as ws:
                    await ws.cmd(f"{DOMAIN}/snapshot")
                print("box is up and Microgreens is loaded")
                return 0
            except (RuntimeError, aiohttp.ClientError):
                await asyncio.sleep(2)
    print("Microgreens never finished loading", file=sys.stderr)
    return 1


async def cmd_setup(_args: argparse.Namespace) -> int:
    async with aiohttp.ClientSession() as session:
        flow = await rest(session, "POST", "/api/config/config_entries/flow", {"handler": DOMAIN})
        if flow.get("type") == "abort":
            print(f"aborted: {flow.get('reason')}")
            return 0
        result = await rest(session, "POST", f"/api/config/config_entries/flow/{flow['flow_id']}", {})
        print(json.dumps({k: result.get(k) for k in ("type", "title", "result")}, indent=2, default=str))
    return 0


async def cmd_ws(args: argparse.Namespace) -> int:
    async with aiohttp.ClientSession() as session, WS(session) as ws:
        print(json.dumps(await ws.cmd(args.type, **_kv(args.fields)), indent=2, ensure_ascii=False))
    return 0


async def cmd_call(args: argparse.Namespace) -> int:
    domain, _, service = args.service.partition(".")
    async with aiohttp.ClientSession() as session:
        print(json.dumps(await rest(session, "POST", f"/api/services/{domain}/{service}", _kv(args.fields)), indent=2))
    return 0


async def cmd_state(args: argparse.Namespace) -> int:
    async with aiohttp.ClientSession() as session:
        print(json.dumps(await rest(session, "GET", f"/api/states/{args.entity}"), indent=2, ensure_ascii=False))
    return 0


async def cmd_notifications(_args: argparse.Namespace) -> int:
    if CAPTURE_FILE.exists():
        for line in CAPTURE_FILE.read_text(encoding="utf-8").splitlines():
            print(line)
    return 0


async def cmd_errors(_args: argparse.Namespace) -> int:
    if LOG_FILE.exists():
        for line in LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            if ("ERROR" in line or "WARNING" in line) and ("microgreens" in line or "Traceback" in line):
                print(line)
    return 0


async def cmd_restart(_args: argparse.Namespace) -> int:
    subprocess.run(["docker", "compose", "restart", "ha"], cwd=HERE, check=True)
    return await cmd_wait(argparse.Namespace(timeout=180))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("wait")
    p.add_argument("--timeout", type=float, default=240)
    p.set_defaults(func=cmd_wait)
    sub.add_parser("onboard").set_defaults(func=cmd_onboard)
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    p = sub.add_parser("ws")
    p.add_argument("type")
    p.add_argument("fields", nargs="*")
    p.set_defaults(func=cmd_ws)
    p = sub.add_parser("call")
    p.add_argument("service")
    p.add_argument("fields", nargs="*")
    p.set_defaults(func=cmd_call)
    p = sub.add_parser("state")
    p.add_argument("entity")
    p.set_defaults(func=cmd_state)
    sub.add_parser("notifications").set_defaults(func=cmd_notifications)
    sub.add_parser("errors").set_defaults(func=cmd_errors)
    sub.add_parser("restart").set_defaults(func=cmd_restart)
    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
