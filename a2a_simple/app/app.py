import logging
import os

import httpx

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from dotenv import load_dotenv

from agent import CurrencyAgent
from agent_executor import CurrencyAgentExecutor


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Get host and port from environment variables (Cloud Foundry sets PORT)
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 10000))

# Create agent capabilities and card
capabilities = AgentCapabilities(streaming=True, push_notifications=True)
skill = AgentSkill(
    id='convert_currency',
    name='Currency Exchange Rates Tool',
    description='Helps with exchange values between various currencies',
    tags=['currency conversion', 'currency exchange'],
    examples=['What is exchange rate between USD and GBP?'],
)
agent_card = AgentCard(
    name='Currency Agent',
    description='Helps with exchange rates for currencies',
    url=f'https://currency-agent.cfapps.sap.hana.ondemand.com',
    version='1.0.0',
    default_input_modes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
    default_output_modes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
    capabilities=capabilities,
    skills=[skill],
)

# Create request handler and server
httpx_client = httpx.AsyncClient()
push_config_store = InMemoryPushNotificationConfigStore()
push_sender = BasePushNotificationSender(
    httpx_client=httpx_client,
    config_store=push_config_store
)
request_handler = DefaultRequestHandler(
    agent_executor=CurrencyAgentExecutor(),
    task_store=InMemoryTaskStore(),
    push_config_store=push_config_store,
    push_sender=push_sender
)
server = A2AStarletteApplication(
    agent_card=agent_card, http_handler=request_handler
)

# Export the ASGI app for uvicorn
app = server.build()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)