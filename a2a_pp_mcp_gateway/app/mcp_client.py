"""MCP-gateway-based S/4 call with principal propagation.

Instead of calling the BTP destination service directly (as the pure
principal-propagation agent did), this agent talks to an **MCP Server hosted
by SAP Integration Suite** (the "MCP Gateway"). The gateway itself resolves
the OAuth2SAMLBearerAssertion destination to S/4 — we only need to forward the
end-user's IAS JWT as the Bearer token on each MCP call.

Chain:  Joule -> A2A agent (this) -> MCP Gateway (Integration Suite) -> S/4

The gateway is secured with an External OAuth (OIDC) inbound policy that trusts
our IAS tenant, so the inbound user JWT (with its `mail` claim) is validated and
its identity propagated down to the SAML Bearer destination. Authorization at the
gateway is done on the `ias_apis` claim (App2App), not on a classic OAuth scope.

This is a deliberately small, dependency-free MCP client over Streamable HTTP
(protocol 2025-06-18): one `MCPSession` context manager that owns the JSON-RPC
handshake (initialize -> notifications/initialized) and a single `call_tool`.
"""
import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

MCP_URL = os.environ["MCP_URL"]
MCP_TOOL = os.environ.get("MCP_TOOL", "get_A_BusinessPartner")
MCP_PROTOCOL_VERSION = os.environ.get("MCP_PROTOCOL_VERSION", "2025-06-18")

_ACCEPT = "application/json, text/event-stream"
_DEFAULT_SELECT = "BusinessPartner,BusinessPartnerName,BusinessPartnerCategory,CreationDate"


def _parse_rpc(resp: requests.Response) -> dict:
    """Parse a JSON-RPC reply that may arrive as plain JSON or an SSE `data:` frame."""
    text = resp.text or ""
    for line in reversed(text.splitlines()):      # last `data:` line wins
        if line.startswith("data:"):
            text = line[len("data:"):].strip()
            break
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return {"_raw": resp.text, "_status": resp.status_code}


class MCPSession:
    """A minimal Streamable-HTTP MCP session, scoped to one user JWT.

    Use as a context manager — it runs the `initialize` + `initialized`
    handshake on enter and carries the returned `mcp-session-id` on every
    subsequent call:

        with MCPSession(user_jwt) as mcp:
            result = mcp.call_tool("get_A_BusinessPartner", {...})
    """

    def __init__(self, user_jwt: str):
        self._base_headers = {
            "Authorization": f"Bearer {user_jwt}",
            "Content-Type": "application/json",
            "Accept": _ACCEPT,
        }
        self._session_id: str | None = None
        self._next_id = 0

    def _rpc(self, method: str, params: dict | None = None, *, notify: bool = False) -> dict:
        """Send one JSON-RPC message. `notify` = fire-and-forget (no id, no result)."""
        body = {"jsonrpc": "2.0", "method": method}
        if not notify:
            self._next_id += 1
            body["id"] = self._next_id
        if params is not None:
            body["params"] = params

        headers = dict(self._base_headers)
        if self._session_id:
            headers["mcp-session-id"] = self._session_id

        resp = requests.post(MCP_URL, headers=headers, json=body, timeout=60)
        if notify:
            return {}
        if resp.status_code != 200:
            raise RuntimeError(f"MCP {method} failed (HTTP {resp.status_code}): {resp.text[:300]}")
        return _parse_rpc(resp)

    def __enter__(self) -> "MCPSession":
        resp = requests.post(
            MCP_URL,
            headers=self._base_headers,
            json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "business-partner-a2a-agent", "version": "1.0"},
                },
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"MCP initialize failed (HTTP {resp.status_code}): {resp.text[:300]}")
        self._session_id = resp.headers.get("mcp-session-id")
        if not self._session_id:
            raise RuntimeError("MCP initialize returned no mcp-session-id header")
        logger.info("MCP gateway session opened: url=%s session=%s", MCP_URL, self._session_id)

        self._rpc("notifications/initialized", notify=True)
        return self

    def __exit__(self, *exc):
        return False

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Invoke a tool and return the parsed JSON-RPC `result`."""
        rpc = self._rpc("tools/call", {"name": name, "arguments": arguments})
        logger.info("MCP tool/call '%s' -> rpc keys=%s", name, list(rpc.keys()))
        if "error" in rpc:
            raise RuntimeError(f"MCP tool error: {rpc['error']}")
        result = rpc.get("result", {})
        if result.get("isError"):
            raise RuntimeError(f"MCP tool returned isError: {result.get('content')}")
        return result


def _odata_arguments(top, filter_expr, select, expand, orderby) -> dict:
    """Map our tool parameters onto the MCP tool's input schema.

    The Integration-Suite-generated tool uses OData query options WITHOUT the
    leading `$`, and `select`/`expand`/`orderby` are arrays of strings.
    """
    def _as_list(value):
        return [p.strip() for p in value.split(",") if p.strip()]

    args: dict = {"top": top, "select": _as_list(select or _DEFAULT_SELECT)}
    if filter_expr:
        args["filter"] = filter_expr
    if expand:
        args["expand"] = _as_list(expand)
    if orderby:
        args["orderby"] = _as_list(orderby)
    return args


def _extract_results(result: dict) -> dict | list:
    """Pull the OData rows out of the MCP tool result (content[0].text is a JSON string)."""
    content = result.get("content") or []
    if content and content[0].get("type") == "text":
        try:
            payload = json.loads(content[0]["text"])
            return payload.get("d", {}).get("results", payload)
        except (ValueError, TypeError):
            return {"raw": content[0]["text"]}
    return result


def call_business_partner_api(
    user_jwt: str,
    top: int = 10,
    filter_expr: str | None = None,
    select: str | None = None,
    expand: str | None = None,
    orderby: str | None = None,
) -> dict | list:
    """Invoke the MCP gateway's business-partner tool as the propagated user.

    Signature mirrors the old direct-S/4 client, so the agent/tool layer is unchanged.
    """
    arguments = _odata_arguments(top, filter_expr, select, expand, orderby)
    with MCPSession(user_jwt) as mcp:
        result = mcp.call_tool(MCP_TOOL, arguments)
    return _extract_results(result)
