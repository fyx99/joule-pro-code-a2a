"""A2A server with async push-notification support for Joule.

Inbound flow:
  1. Joule sends a request to this agent. The A2A SDK routes it to our
     CurrencyAgentExecutor.
  2. The executor pulls the user JWT and correlation headers straight off
     the A2A RequestContext (`context._call_context.state["headers"]`).
  3. Heartbeats and the final result are POSTed to Joule's async callback URL
     via `joule_client`, which delegates the OAuth exchange to the BTP
     Destination Service.
"""
import logging
import os

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv

from agent import CurrencyAgent
from agent_executor import CurrencyAgentExecutor


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 10000))
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://currency-agent-async.cfapps.sap.hana.ondemand.com")


# --- Agent card -------------------------------------------------------------
agent_card = AgentCard(
    name="Currency Agent (Async)",
    description="Currency exchange agent that responds asynchronously via push notifications.",
    url=PUBLIC_URL,
    version="1.0.0",
    default_input_modes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
    default_output_modes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
    capabilities=AgentCapabilities(streaming=True, push_notifications=True),
    skills=[
        AgentSkill(
            id="convert_currency",
            name="Currency Exchange Rates Tool",
            description="Helps with exchange values between various currencies",
            tags=["currency conversion", "currency exchange"],
            examples=["What is exchange rate between USD and GBP?"],
        )
    ],
)


# --- A2A server -------------------------------------------------------------
request_handler = DefaultRequestHandler(
    agent_executor=CurrencyAgentExecutor(),
    task_store=InMemoryTaskStore(),
)
server = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
app = server.build()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
