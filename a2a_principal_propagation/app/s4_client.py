"""Destination-service-based S/4 call with principal propagation.

Implements the steps from the test chapter of the blog:
  Step 2: Destination Service Token (Client Credentials)
  Step 3: Find Destination + X-user-token -> S/4 OAuth Token (SAML Bearer Flow)
  Step 4: API call to the S/4 Business Partner endpoint
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

DEST_SERVICE_URL   = os.environ["DEST_SERVICE_URL"]      # e.g. https://destination-configuration.cfapps.eu10.hana.ondemand.com
DEST_TOKEN_URL     = os.environ["DEST_TOKEN_URL"]        # XSUAA token endpoint from the dest-service binding
DEST_CLIENT_ID     = os.environ["DEST_CLIENT_ID"]
DEST_CLIENT_SECRET = os.environ["DEST_CLIENT_SECRET"]
DEST_NAME          = os.environ.get("DEST_NAME", "S4_PUBLIC_OAUTHSAMLBEAERER")


def _get_dest_service_token() -> str:
    """Step 2: Client-credentials token for the Destination Service."""
    r = requests.post(
        DEST_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(DEST_CLIENT_ID, DEST_CLIENT_SECRET),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _resolve_destination(user_jwt: str) -> dict:
    """Step 3: Resolve the destination using X-user-token.

    The Destination Service:
      1. Validates the IAS token (jwks_uri from the additional properties)
      2. Extracts the user from the mail claim (userIdSource=mail)
      3. Generates a SAML assertion with the user identity
      4. Exchanges the SAML assertion for an S/4 OAuth token
    """
    dest_token = _get_dest_service_token()
    r = requests.get(
        f"{DEST_SERVICE_URL}/destination-configuration/v1/destinations/{DEST_NAME}",
        headers={
            "Authorization": f"Bearer {dest_token}",
            "X-user-token": user_jwt,   # drives principal propagation
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def call_business_partner_api(
    user_jwt: str,
    top: int = 10,
    filter_expr: str | None = None,
    select: str | None = None,
    expand: str | None = None,
    orderby: str | None = None,
) -> dict:
    """Step 4: API call against the S/4 Business Partner endpoint with the propagated user.

    Args:
        user_jwt: IAS JWT of the logged-in user (for principal propagation).
        top: Number of rows ($top).
        filter_expr: OData $filter (e.g. "Country eq 'DE'").
        select: OData $select. None -> sensible default set for demos.
        expand: OData $expand (e.g. "to_BusinessPartnerAddress").
        orderby: OData $orderby (e.g. "BusinessPartnerName asc").
    """
    dest = _resolve_destination(user_jwt)
    auth_tokens = dest.get("authTokens") or []
    if not auth_tokens or auth_tokens[0].get("error"):
        err = auth_tokens[0].get("error") if auth_tokens else "no authTokens returned"
        raise RuntimeError(f"Destination service did not issue a token: {err}")

    s4_token = auth_tokens[0]["value"]
    base_url = dest["destinationConfiguration"]["URL"]

    params = {
        "$format": "json",
        "$top": top,
        "$select": select or "BusinessPartner,BusinessPartnerName,BusinessPartnerCategory,CreationDate",
    }
    if filter_expr:
        params["$filter"] = filter_expr
    if expand:
        params["$expand"] = expand
    if orderby:
        params["$orderby"] = orderby

    r = requests.get(
        f"{base_url}/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_BusinessPartner",
        headers={"Authorization": f"Bearer {s4_token}", "Accept": "application/json"},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    return payload.get("d", {}).get("results", payload)
