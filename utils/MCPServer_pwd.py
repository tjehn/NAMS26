# =============================================================================
# File     : utils/MCPServer_pwd.py
# Purpose  : Read-only MCP server for NAMS26 lab validation.
#            Allows Claude to run show commands against live lab routers
#            during module development. Password auth variant.
#            Tools: run_show (single device), run_show_all (all routers)
# Auth     : Password — reads ROUTER_USERNAME / ROUTER_PASSWORD from .env
# Inventory: utils/hosts.yaml (project-root host inventory)
# Transport: Scrapli asyncssh with legacy IOL algorithm support
# Usage    : python utils/MCPServer_pwd.py
# =============================================================================

import asyncio
import os
import time

import yaml
from dotenv import load_dotenv
from fastmcp import FastMCP
from scrapli.driver.core import AsyncIOSXEDriver

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
HOSTS_FILE   = os.path.join(SCRIPT_DIR, "hosts.yaml")
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

mcp = FastMCP("nams26_lab_validation")

# Legacy algorithm sets required by Cisco IOL 15.x — not offered by modern SSH by default.
TRANSPORT_OPTIONS = {
    "asyncssh": {
        "kex_algs": [
            "diffie-hellman-group14-sha1",
            "diffie-hellman-group-exchange-sha1",
            "diffie-hellman-group1-sha1",
        ],
        "encryption_algs": [
            "aes128-ctr",
            "aes192-ctr",
            "aes256-ctr",
            "aes128-cbc",
            "3des-cbc",
        ],
        "mac_algs": [
            "hmac-sha1",
            "hmac-sha1-96",
        ],
        "server_host_key_algs": [
            "ssh-rsa",
        ],
    }
}

SWITCH_NAMES = {"COSW-01", "COSW-02", "OOB_SW01"}


def _load_inventory() -> dict:
    with open(HOSTS_FILE) as f:
        return yaml.safe_load(f)


def _credentials(device_data: dict) -> tuple[str, str]:
    username = os.getenv("ROUTER_USERNAME") or device_data["credentials"]["username"]
    password = os.getenv("ROUTER_PASSWORD") or device_data["credentials"]["password"]
    return username, password


async def _run_command(host: str, username: str, password: str, command: str) -> str:
    async with AsyncIOSXEDriver(
        host=host,
        auth_username=username,
        auth_password=password,
        auth_strict_key=False,
        transport="asyncssh",
        transport_options=TRANSPORT_OPTIONS,
    ) as conn:
        result = await conn.send_command(command)
        return result.result


@mcp.tool()
async def run_show(device: str, command: str) -> str:
    """Run a single show command against a single named device.

    Args:
        device: Device name from inventory (e.g. R1, R2, COSW-01)
        command: Show command to run (e.g. 'show ip route', 'show isis neighbors')
    """
    inventory = _load_inventory()
    hosts = inventory.get("hosts", {})

    if device not in hosts:
        valid = ", ".join(sorted(hosts.keys()))
        return f"Unknown device '{device}'. Valid devices: {valid}"

    device_data = hosts[device]
    username, password = _credentials(device_data)

    try:
        output = await _run_command(device_data["dns_name"], username, password, command)
        return f"{device}# {command}\n{output}"
    except Exception as e:
        return f"Error connecting to {device} ({device_data['dns_name']}): {e}"


@mcp.tool()
async def run_show_all(command: str, include_switches: bool = False) -> dict:
    """Run the same show command against all routers simultaneously.

    Args:
        command: Show command to run against all routers
        include_switches: Include COSW-01, COSW-02, OOB_SW01 in the query (default: False)
    """
    inventory = _load_inventory()
    hosts = inventory.get("hosts", {})

    if include_switches:
        targets = list(hosts.keys())
    else:
        targets = [name for name in hosts if name not in SWITCH_NAMES]

    async def query(name: str) -> tuple[str, str]:
        device_data = hosts[name]
        username, password = _credentials(device_data)
        try:
            output = await _run_command(device_data["dns_name"], username, password, command)
            return name, output
        except Exception as e:
            return name, f"ERROR: {e}"

    start = time.monotonic()
    results = await asyncio.gather(*[query(name) for name in targets], return_exceptions=True)
    elapsed = round(time.monotonic() - start, 2)

    output: dict = {}
    for item in results:
        if isinstance(item, Exception):
            output["_gather_error"] = f"ERROR: {item}"
        else:
            name, result = item
            output[name] = result

    output["_execution_time_seconds"] = elapsed
    return output


if __name__ == "__main__":
    mcp.run()
