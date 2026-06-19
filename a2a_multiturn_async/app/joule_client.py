"""Destination-service-based Joule async-callback with principal propagation.

Mirror of `a2a_principal_propagation/app/s4_client.py` — same sequence of steps,
same env-var names, same destination-service mechanics — but the destination
points at Joule's async callback URL instead of an S/4 endpoint, and the
exchanged token is used to POST the agent's result back to Joule.

Steps:
  1. Destination Service Token (Client Credentials)
  2. Find Destination + X-user-token -> Joule async-api JWT (JWT Bearer Flow)
  3. POST the JSON-RPC envelope to the resolved callback URL
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEST_SERVICE_URL   = os.environ["DEST_SERVICE_URL"]      # e.g. https://destination-configuration.cfapps.eu10.hana.ondemand.com
DEST_TOKEN_URL     = os.environ["DEST_TOKEN_URL"]        # XSUAA token endpoint from the dest-service binding
DEST_CLIENT_ID     = os.environ["DEST_CLIENT_ID"]
DEST_CLIENT_SECRET = os.environ["DEST_CLIENT_SECRET"]
DEST_NAME          = os.environ.get("DEST_NAME", "JOULE_ASYNC_API")


async def _get_dest_service_token(http: httpx.AsyncClient) -> str:
    """Step 1: Client-credentials token for the Destination Service."""
    r = await http.post(
        DEST_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(DEST_CLIENT_ID, DEST_CLIENT_SECRET),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def _resolve_destination(http: httpx.AsyncClient, user_jwt: str) -> dict:
    """Step 2: Resolve the destination using X-user-token.

    The Destination Service:
      1. Validates the IAS user token (jwks_uri from the additional properties)
      2. Runs the JWT-bearer exchange against the IAS app behind the destination
      3. Returns the resulting Joule async-api JWT in authTokens[0].value
    """
    dest_token = await _get_dest_service_token(http)
    r = await http.get(
        f"{DEST_SERVICE_URL}/destination-configuration/v1/destinations/{DEST_NAME}",
        headers={
            "Authorization": f"Bearer {dest_token}",
            "X-user-token": user_jwt,   # drives token exchange from current user context
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# --- JSON-RPC envelope builders ---------------------------------------------
# Joule expects the A2A `Task` wrapped in a JSON-RPC envelope. These three
# helpers cover the states an agent ever needs to report back:
#   - working           : intermediate status update ("Looking up rates...")
#   - input-required    : pause and ask the user a follow-up question
#   - completed         : final answer (carries the artifact)

def _envelope(task_id: str, context_id: str, correlation_id: str, result: dict) -> dict:
    return {
        "id": correlation_id or task_id,
        "jsonrpc": "2.0",
        "result": {
            "id": task_id,
            "contextId": context_id,
            "kind": "task",
            **result,
        },
    }


def _status_message(task_id: str, message: str) -> dict:
    return {
        "messageId": f"msg-{task_id}",
        "kind": "message",
        "role": "agent",
        "parts": [{"kind": "text", "text": message}],
    }


def working_envelope(task_id: str, context_id: str, correlation_id: str, message: str) -> dict:
    """Intermediate `working` push (no artifact yet)."""
    return _envelope(task_id, context_id, correlation_id, {
        "status": {"state": "working", "message": _status_message(task_id, message)},
    })


def input_required_envelope(task_id: str, context_id: str, correlation_id: str, message: str) -> dict:
    """Pause and ask the user a follow-up question."""
    return _envelope(task_id, context_id, correlation_id, {
        "status": {"state": "input-required", "message": _status_message(task_id, message)},
    })


def completed_envelope(task_id: str, context_id: str, correlation_id: str, message: str) -> dict:
    """Final result. The `artifacts` field is what shows up as the assistant message in Joule."""
    return _envelope(task_id, context_id, correlation_id, {
        "status": {"state": "completed"},
        "artifacts": [{
            "artifactId": f"result-{task_id}",
            "parts": [{"kind": "text", "text": message}],
        }],
    })


# --- Callback POST ----------------------------------------------------------

async def post_callback(
    http: httpx.AsyncClient,
    user_jwt: str,
    conversation_id: str,
    correlation_id: str,
    body: dict,
) -> httpx.Response:
    """Step 3: POST the JSON-RPC envelope to Joule's async callback URL.

    Resolves the destination first to obtain both the Joule-side URL and the
    exchanged JWT, then issues the callback. Joule requires the original
    `conversationid` / `x-correlationid` headers on the callback so it can
    route the result back to the right conversation.
    """
    dest = await _resolve_destination(http, user_jwt)

    auth_tokens = dest.get("authTokens") or []
    if not auth_tokens or auth_tokens[0].get("error") or not auth_tokens[0].get("value"):
        err = (auth_tokens[0].get("error") if auth_tokens else None) or "no authTokens returned"
        raise RuntimeError(f"Destination service did not issue a token: {err}")

    callback_url = dest["destinationConfiguration"]["URL"]
    headers = {
        auth_tokens[0]["http_header"]["key"]: auth_tokens[0]["http_header"]["value"],
        "Content-Type": "application/json",
        "conversationid": conversation_id,
        "x-correlationid": correlation_id,
    }
    return await http.post(callback_url, json=body, headers=headers)
