# A2A Agent with IAS Auth - CURL Examples

## Step 1: Get OAuth Token from IAS

```bash
TOKEN=$(curl -s -X POST "https://<your-tenant>.accounts.ondemand.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=<your-client-id>" \
  -d "client_secret=<your-client-secret>" | jq -r '.access_token')

echo "Token: ${TOKEN:0:50}..."
```

## Step 2: Get Agent Card (No Auth Required)

```bash
curl -s "https://<your-agent>.cfapps.sap.hana.ondemand.com/.well-known/agent.json" | jq '.'
```

**Response:**
```json
{
  "name": "Currency Agent",
  "description": "Helps with exchange rates for currencies",
  "version": "1.0.0",
  "protocolVersion": "0.3.0",
  "capabilities": {
    "pushNotifications": true,
    "streaming": true
  },
  "skills": [
    {
      "id": "convert_currency",
      "name": "Currency Exchange Rates Tool",
      "description": "Helps with exchange values between various currencies"
    }
  ]
}
```

## Step 3: Test Without Auth (Should Fail)

```bash
curl -s "https://<your-agent>.cfapps.sap.hana.ondemand.com/" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "message/send", "params": {}, "id": "1"}' | jq '.'
```

**Response:**
```json
{
  "detail": "Missing token"
}
```

## Step 4: Send Message to Agent (With Auth)

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

**Response:**
```json
{
  "id": "1",
  "jsonrpc": "2.0",
  "result": {
    "artifacts": [
      {
        "artifactId": "ad8b315f-dd87-45ca-9f5e-584439102732",
        "name": "conversion_result",
        "parts": [
          {
            "kind": "text",
            "text": "100 USD is approximately 86.77 EUR based on the current exchange rate."
          }
        ]
      }
    ],
    "contextId": "095d62bd-dfa1-4b77-991b-392fe7038ecd",
    "id": "639c1a4b-d486-45df-b4be-4b614e0c441d",
    "kind": "task",
    "status": {
      "state": "completed",
      "timestamp": "2026-04-07T11:44:14.740338+00:00"
    }
  }
}
```

## Reference

- **Agent URL**: https://<your-agent>.cfapps.sap.hana.ondemand.com
- **Auth**: OAuth 2.0 Bearer Token (SAP IAS, client_credentials flow)
- **Public Endpoints** (no auth): `/.well-known/*`
- **Protocol**: JSON-RPC 2.0, method `message/send`
