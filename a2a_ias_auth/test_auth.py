"""Simple test script for IAS authenticated A2A agent."""

import asyncio
import httpx

# Configuration - Replace with your values
AGENT_URL = "https://<your-agent>.cfapps.sap.hana.ondemand.com"
AUTH_URL = "https://<your-ias-tenant>.accounts.ondemand.com"
CLIENT_ID = "<your-ias-client-id>"
CLIENT_SECRET = "<your-ias-client-secret>"


async def get_token(client: httpx.AsyncClient) -> str:
    """Get OAuth token from IAS using client credentials."""
    print("🔐 Getting OAuth token from IAS...")

    response = await client.post(
        f"{AUTH_URL}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        raise Exception(f"Token request failed: {response.status_code} - {response.text}")

    token_data = response.json()
    print(f"✅ Token obtained (expires in {token_data.get('expires_in', '?')}s)")
    return token_data["access_token"]


async def test_without_auth(client: httpx.AsyncClient):
    """Test that protected endpoint returns 401 without auth."""
    print("\n🔒 Testing without auth (should fail)...")

    response = await client.post(
        f"{AGENT_URL}/",
        json={"jsonrpc": "2.0", "method": "message/send", "params": {}, "id": "1"},
    )

    if response.status_code == 401:
        print(f"✅ Correctly rejected: {response.json()}")
    else:
        print(f"⚠️  Expected 401, got {response.status_code}: {response.text}")


async def send_message(client: httpx.AsyncClient, token: str, message: str):
    """Send message to agent with auth."""
    print(f"\n💬 Sending: '{message}'")

    response = await client.post(
        f"{AGENT_URL}/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": message}],
                    "messageId": "msg-123"
                }
            },
            "id": "1",
        },
        timeout=30.0,
    )

    result = response.json()
    print(f"✅ Response: {result}")
    return result


async def main():
    print("=" * 60)
    print("🧪 Testing IAS Auth for A2A Agent")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Test 1: Should fail without auth
        await test_without_auth(client)

        # Test 2: Get token
        token = await get_token(client)

        # Test 3: Send message with auth
        await send_message(client, token, "What is 100 USD in EUR?")

        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
