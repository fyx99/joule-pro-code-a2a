# Joule Pro-Code A2A Examples

This repository contains examples for integrating custom AI agents with SAP Joule using the A2A (Agent-to-Agent) protocol.

## Repository Structure

```
joule-pro-code-a2a/
├── a2a_simple/          # Basic A2A agent without authentication
├── a2a_ias_auth/        # A2A agent with SAP IAS authentication
└── images/              # Shared images for blog posts
```

### a2a_simple

A minimal example demonstrating how to build and deploy a LangGraph-based currency conversion agent to Cloud Foundry and integrate it with Joule via the A2A protocol.

**Features:**
- LangGraph ReAct agent with currency conversion tool
- A2A SDK server setup
- Joule Pro-Code capability configuration
- No authentication (for learning purposes)

See [a2a_simple/blog.md](a2a_simple/blog.md) for the full tutorial.

### a2a_ias_auth

Extends the simple example with SAP Cloud Identity Services (IAS) authentication to protect the agent from unauthorized access.

**Features:**
- JWT token validation middleware
- IAS client credentials flow
- Public discovery endpoints (`/.well-known/`)
- Protected agent endpoints

See [a2a_ias_auth/blog-a2a-auth-draft.md](a2a_ias_auth/blog-a2a-auth-draft.md) for the full tutorial.

## Related Blog Posts

- [Integrating Custom Agents with Joule via A2A](https://community.sap.com/t5/technology-blogs-by-sap/...) - Basic integration
- [Using IAS to Secure Python APIs on Cloud Foundry](https://community.sap.com/t5/technology-blogs-by-sap/using-ias-to-secure-python-apis-on-cloud-foundry/ba-p/13960702) - IAS setup basics
