# Joule Pro-Code A2A Examples

A hands-on blog series on connecting custom, code-based agents on SAP BTP to **SAP Joule** via the **A2A (Agent-to-Agent) protocol** — from a minimal agent all the way to principal propagation into S/4HANA.

Each example lives in its own folder with a runnable agent and a `blog.md` walking through the setup. The posts build on each other, so the order below is also the recommended reading order.

## Examples

### [`a2a_simple`](a2a_simple/blog.md)
A minimal viable A2A agent: a LangGraph ReAct currency-conversion agent, served via the A2A SDK, deployed to Cloud Foundry and wired into Joule as a pro-code capability. No authentication — the starting point for the series.

### [`a2a_ias_auth`](a2a_ias_auth/blog.md)
Secures the agent with **SAP Cloud Identity Services (IAS)**. Adds JWT-validation middleware and the OAuth2 client-credentials flow so only authorized callers (e.g. Joule) reach the agent, while keeping the `/.well-known/` discovery endpoints public.

### [`a2a_multiturn`](a2a_multiturn/a2a_multiturn_blog.md)
Enables **multi-turn conversations** using the A2A protocol's context management (`contextId` / `taskId`), so the agent can ask follow-up questions and keep state across turns instead of forgetting everything after each message.

### [`a2a_multiturn_async`](a2a_multiturn_async/blog.md)
Extends multi-turn to **asynchronous communication** for long-running tasks that don't fit the synchronous request/response window — the agent accepts work and pushes results back to Joule when ready.

### [`a2a_principal_propagation`](a2a_principal_propagation/blog.md)
**Principal propagation** end-to-end: from the Joule-managed IAS application into S/4HANA Public Cloud via a two-hop IAS token exchange and a SAML 2.0 Bearer flow through the BTP Destination Service. The agent holds no long-lived backend credentials — every call runs as the real logged-in user.

### [`a2a_pp_mcp_gateway`](a2a_pp_mcp_gateway/blog.md)
The same principal-propagation scenario, but the agent reaches S/4HANA through the **SAP Integration Suite MCP Gateway** instead of calling the Destination Service directly: it forwards the user JWT to the MCP endpoint, which resolves the destination on the user's behalf.

### [`a2a_cmj_to_smj`](a2a_cmj_to_smj/blog.md)
Conceptual overview (state: November 2026): the migration paths for custom BTP-based agents from **Customer-Managed Joule (CMJ)** to **SAP-Managed Joule / Joule Work (SMJ)**, framed by the SAP reference architecture for A2A and MCP interoperability.

## Repository layout

```
joule-pro-code-a2a/
├── a2a_simple/                  # Minimal A2A agent (no auth)
├── a2a_ias_auth/                # + IAS authentication
├── a2a_multiturn/               # + multi-turn context handling
├── a2a_multiturn_async/         # + asynchronous communication
├── a2a_principal_propagation/   # + principal propagation into S/4HANA
├── a2a_pp_mcp_gateway/          # principal propagation via MCP Gateway
├── a2a_cmj_to_smj/              # CMJ -> SMJ migration options (concept)
└── images/                      # Shared images for the blog posts
```

## Notes

All credentials, tenant identifiers and personal data in the examples are placeholders — replace them with your own values before deploying.
