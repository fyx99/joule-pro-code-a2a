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

from agent import BusinessPartnerAgent
from agent_executor import BusinessPartnerAgentExecutor
from middleware.ias_auth import AuthMiddleware


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Get host and port from environment variables (Cloud Foundry sets PORT)
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 10000))

# Create agent capabilities and card
capabilities = AgentCapabilities(streaming=True, push_notifications=True)
business_partner_skill = AgentSkill(
    id='get_business_partners',
    name='S/4HANA Business Partner Lookup',
    description='Lists business partners / customers from S/4HANA on behalf of the logged-in user (principal propagation via SAML Bearer).',
    tags=['s4hana', 'business partner', 'customer', 'principal propagation'],
    examples=[
        'Show me business partners from S/4HANA',
        'List 2 customers',
        'Get business partners',
    ],
)
agent_card = AgentCard(
    name='Business Partner Agent',
    description='Looks up business partners and customers from S/4HANA on behalf of the logged-in user (principal propagation).',
    url=f'https://business-partner-agent-principal-propagation.cfapps.sap.hana.ondemand.com',
    version='1.0.0',
    default_input_modes=BusinessPartnerAgent.SUPPORTED_CONTENT_TYPES,
    default_output_modes=BusinessPartnerAgent.SUPPORTED_CONTENT_TYPES,
    capabilities=capabilities,
    skills=[business_partner_skill],
)

# Create request handler and server
httpx_client = httpx.AsyncClient()
push_config_store = InMemoryPushNotificationConfigStore()
push_sender = BasePushNotificationSender(
    httpx_client=httpx_client,
    config_store=push_config_store
)
request_handler = DefaultRequestHandler(
    agent_executor=BusinessPartnerAgentExecutor(),
    task_store=InMemoryTaskStore(),
    push_config_store=push_config_store,
    push_sender=push_sender
)
server = A2AStarletteApplication(
    agent_card=agent_card, http_handler=request_handler
)

# Build app
app = server.build()

# Auth Middleware: validates IAS token and checks required scope.
app.add_middleware(AuthMiddleware)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
