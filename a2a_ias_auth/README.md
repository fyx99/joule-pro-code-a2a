# A2A Agent with IAS Authentication

A2A (Agent-to-Agent) SDK server deployed to SAP BTP Cloud Foundry with SAP IAS authentication.

## Architecture

```
Client Request → IAS Auth Middleware → A2A Server → Agent Executor
```

## Prerequisites

- SAP BTP Cloud Foundry account
- Cloud Foundry CLI (`cf`)
- Python 3.11+
- SAP IAS tenant with:
  - Client ID
  - Client Secret (with `api_read_access` scope)
  - Tenant URL (e.g., `https://your-tenant.accounts.ondemand.com`)

## Setup

### 1. Configure IAS Application

Create an application in SAP IAS with client credentials. See [Using IAS to Secure Python APIs on Cloud Foundry](https://community.sap.com/t5/technology-blogs-by-sap/using-ias-to-secure-python-apis-on-cloud-foundry/ba-p/13960702) for details.

### 2. Update manifest.yaml

Edit `app/manifest.yaml` with your credentials:

```yaml
env:
  IAS_ISSUER: "https://your-tenant.accounts.ondemand.com"
  IAS_AUDIENCE: "your-client-id"
  # Also add your AI Core credentials
```

### 3. Deploy

```bash
cd app
cf push
```

## Testing

### Using the Test Script

Edit `test_auth.py` and set your credentials:

```python
AGENT_URL = "https://<your-agent>.cfapps.sap.hana.ondemand.com"
AUTH_URL = "https://<your-ias-tenant>.accounts.ondemand.com"
CLIENT_ID = "<your-ias-client-id>"
CLIENT_SECRET = "<your-ias-client-secret>"
```

Then run:

```bash
python test_auth.py
```

The script will:
1. Test that requests without token return 401
2. Get an OAuth token from IAS
3. Send a message to the agent with the token

### Using cURL

**Get OAuth Token:**

```bash
TOKEN=$(curl -s -X POST "https://<your-tenant>.accounts.ondemand.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=<your-client-id>" \
  -d "client_secret=<your-client-secret>" | jq -r '.access_token')
```

**Get Agent Card (no auth required):**

```bash
curl -s "https://<your-agent>.cfapps.sap.hana.ondemand.com/.well-known/agent.json" | jq '.'
```

**Test without auth (should return 401):**

```bash
curl -s "https://<your-agent>.cfapps.sap.hana.ondemand.com/" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "message/send", "params": {}, "id": "1"}'
```

**Send message with auth:**

```bash
curl -s "https://<your-agent>.cfapps.sap.hana.ondemand.com/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "What is 100 USD in EUR?"}],
        "messageId": "msg-123"
      }
    },
    "id": "1"
  }' | jq '.'
```

## Project Structure

```
a2a_ias_auth/
├── app/
│   ├── app.py              # Main server
│   ├── agent.py            # Currency agent
│   ├── agent_executor.py   # Agent executor
│   ├── middleware/
│   │   └── ias_auth.py     # IAS auth middleware
│   ├── manifest.yaml       # CF deployment config
│   ├── requirements.txt
│   └── runtime.txt
├── currency_agent_capability/  # Joule capability config
├── test_auth.py            # Test script
├── blog-a2a-auth-draft.md  # Blog post
└── README.md
```

## Public Endpoints

`/.well-known/*` paths are public (no auth required) for agent discovery.

All other endpoints require a valid IAS Bearer token.
