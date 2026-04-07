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
- SAP IAS tenant with client credentials

## Setup

### 1. Configure IAS Application

Create an application in SAP IAS and note:
- Client ID
- Client Secret
- Tenant URL (e.g., `https://your-tenant.accounts.ondemand.com`)

### 2. Set Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
IAS_ISSUER=https://your-tenant.accounts.ondemand.com
IAS_AUDIENCE=your-client-id
```

### 3. Deploy

```bash
cd app
cf push
```

## Testing

Run the test script:

```bash
python test_auth.py
```

Or use curl (see `TEST_CURL_COMMANDS.md`):

```bash
# Get token
TOKEN=$(curl -s -X POST "https://<tenant>.accounts.ondemand.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=<client-id>" \
  -d "client_secret=<client-secret>" | jq -r '.access_token')

# Call agent
curl -s "https://<your-agent>.cfapps.sap.hana.ondemand.com/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "message/send", "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": "What is 100 USD in EUR?"}], "messageId": "msg-123"}}, "id": "1"}'
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
├── test_auth.py            # Test script
├── .env.example
├── TEST_CURL_COMMANDS.md
└── README.md
```

## Public Endpoints

`/.well-known/*` paths are public (no auth required) for agent discovery.

All other endpoints require a valid IAS Bearer token.
