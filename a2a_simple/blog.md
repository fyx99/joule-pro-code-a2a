Many organizations began early by developing their own AI agents and assistants, frequently using frameworks such as LangChain and LangGraph. This post demonstrates how a custom-built AI agent can be integrated into the Joule ecosystem by using the recently introduced pro-code extensibility features together with the A2A integration.

For the demonstration, a minimal ReAct agent implemented in Python with LangGraph is used.

![Joule A2A Custom Agent](../images/joule%20a2a%20custom%20agent.png)

The **A2A Protocol (Agent2Agent Protocol)** is an open standard developed to enable seamless communication and collaboration between autonomous AI agents built by different vendors and on different frameworks. It defines a common interaction model that allows agents to discover each other's capabilities, exchange structured messages and tasks, and coordinate actions securely without exposing internal state or proprietary logic.

The protocol uses standardized components such as Agent Cards for capability discovery and supports multiple transport bindings including HTTP(S) and JSON-RPC 2.0. A2A is designed with enterprise requirements in mind, supporting asynchronous task workflows, secure communication, and interoperability across diverse agent ecosystems. Find details [here](https://github.com/google/A2A).

Many practitioners in the community have already experimented with Joule Studio as the low-code environment for extending Joule. Joule now also provides pro-code extensibility. This expands the addressable scenarios beyond classic skills, enabling more complex logic, deeper structures, richer response shaping, and integration with remote agents via A2A.

### Overview of Joule Capabilities

Within the pro-code model, developers define capabilities. A capability groups the "skills" Joule can invoke in response to a user request.

Two concepts are central: **scenarios** and **functions**.

* A **scenario** acts as the entry shell of a skill. It contains a name, a description, and a set of input parameters. During skill selection, Joule evaluates the scenario description of the available list of scenarios to pick one. The scenario itself then declares which function should run and which parameters will be filled by Joule.
* A **function** represents the executable logic. It is composed of smaller actions, for example, calling an API, sending or formatting messages, or—now newly—invoking another remote agent.

From an engineering perspective, these artifacts are authored as YAML projects and then deployed to a Joule instance.

To support this workflow, two primary tools are available: the Joule Studio Code Editor extension for Visual Studio Code, and the Joule Studio CLI. The example here focuses primarily on using the CLI.

Now let's go step by step:

---

## Setup

For this exercise, there are two prerequisites:

**First**, you need to have an instance of Joule base instantiated on one of your BTP Subaccounts. If you do not yet have one, I recommend checking out our great mission around Joule Studio that includes a step to set up a minimal setup of Joule. Ideally, your company already enabled Joule for some of the Cloud applications, and you can utilize that instance. In the mission, they explain how to set up your user with the "end_user" role in BTP. For this exercise, we need some additional roles ("capability_admin", "extensibility_developer") as depicted below:

![Joule Roles](../images/joule%20roles.png)

**Second**, to engage in the Pro-Code extensibility, you want to have the Joule CLI installed. Here I recommend checking out the newly released Joule Developer documentation on help.sap.

To log in against your Joule application, there are some additional steps necessary. We need to collect a set of client credentials. Since Joule is based on the new Cloud Identity Services flow, this involves a few extra steps.

#### 1. Login to your IAS tenant:

On your BTP Subaccount where you set up Joule, you trusted an IAS tenant—found under Trust Configuration. You will need to navigate to its Admin Panel by appending `/admin` to the tenant URL.

#### 2. Create new Application:

In the IAS admin panel, navigate to "Application & Resources" > "Applications". In there, you see a full list of all registered applications on that IAS tenant. Now we need to create a new one by hitting "Create". In the pop-up, we give it any name, select OpenID Connect, and leave the rest of the fields as is.

![Joule CLI Secret](../images/joule%20clie%20application%20create.png)

#### 3. Add Joule application as a dependency:

Once the Application is created, we need to add a Dependency to that Application. For that purpose, we select the newly created application and navigate to "Dependencies". By clicking on "Add" we will be able to add a new one. In the pop-up, we need to give it the name "Cli2Joule". This name is mandatory.

Next, we select the Joule application—you will recognize your subaccount name after the "das-ias". Finally, we can select the API and hit "Save".

![Joule Client Secret Add](../images/joule%20client%20secret%20add.png)

#### 4. Create Client Secret:

The following step will be to navigate to "Client Authentication", still under your own created app. We want to add a new Secret by clicking "Add". Giving it an arbitrary name and ticking all the boxes will lead to its creation:

![Joule Client Auth Add](../images/joule%20client%20auth%20add.png)

Now with that, we have all the necessary details to log in to Joule:

```
joule login 
✔ Authentication URL: https://<tenant-id>.accounts.ondemand.com    # IAS domain
✔ API URL: https://<subdomain>.<region>.sapdas.cloud.sap           # Joule domain
✔ Instance Client ID: <client-id>                                  # client_id created above
✔ Instance Client Secret: <client-secret>                          # client_id created above
✔ Username: felix.lastname@company.com                             # personal user in IAS with the roles mentioend above
✔ Password: <password>                                             # password to that user in IAS - if you use OTP multifactor - be aware of https://me.sap.com/notes/0003055323

API URL: https://<subdomain>.<region>.sapdas.cloud.sap
You are logged in as felix.lastname@company.com
```

**Note:** The Authentication URL is the Domain of your IAS tenant, so you can easily copy it from the admin panel's URL.

**Note:** The API URL is the URL of Joule, so when opening up your Joule application from the BTP, you can copy that one:

![Joule API URL](../images/joule%20api%20url.png)

---

## 1. Building the Agent with LangGraph

The first step in this journey is to build an AI agent and expose it via an A2A server. For this purpose, I am using the samples provided directly by the A2A project on GitHub.

Since LangGraph is a popular framework, I am using the LangGraph sample code here. However, you could replace it with any framework you prefer. Similarly, the programming language is flexible: A2A only defines the endpoint structure and schema. You can expose A2A servers using any technology you like. Sample code is available for a variety of languages, including Node.js and Java. For my demonstration, I am using Python deployed on SAP Cloud Foundry.

My project structure, adapted for deployment on Cloud Foundry, looks like this:

```
app/
├── agent.py
├── agent_executor.py
├── app.py
├── manifest.yaml
├── requirements.txt
├── runtime.txt
└── test_client.py
```

First, let's look at the heart of our project—the `agent.py`:

```python
import os

from collections.abc import AsyncIterable
from typing import Any, Literal

import httpx

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
from gen_ai_hub.proxy.core.proxy_clients import get_proxy_client

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

proxy_client = get_proxy_client('gen-ai-hub')


memory = MemorySaver()


@tool
def get_exchange_rate(
    currency_from: str = 'USD',
    currency_to: str = 'EUR',
    currency_date: str = 'latest',
):
    """Use this to get current exchange rate.

    Args:
        currency_from: The currency to convert from (e.g., "USD").
        currency_to: The currency to convert to (e.g., "EUR").
        currency_date: The date for the exchange rate or "latest". Defaults to
            "latest".

    Returns:
        A dictionary containing the exchange rate data, or an error message if
        the request fails.
    """
    try:
        response = httpx.get(
            f'https://api.frankfurter.app/{currency_date}',
            params={'from': currency_from, 'to': currency_to},
        )
        response.raise_for_status()

        data = response.json()
        if 'rates' not in data:
            return {'error': 'Invalid API response format.'}
        return data
    except httpx.HTTPError as e:
        return {'error': f'API request failed: {e}'}
    except ValueError:
        return {'error': 'Invalid JSON response from API.'}


class ResponseFormat(BaseModel):
    """Respond to the user in this format."""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str


class CurrencyAgent:
    """CurrencyAgent - a specialized assistant for currency convesions."""

    SYSTEM_INSTRUCTION = (
        'You are a specialized assistant for currency conversions. '
        "Your sole purpose is to use the 'get_exchange_rate' tool to answer questions about currency exchange rates. "
        'If the user asks about anything other than currency conversion or exchange rates, '
        'politely state that you cannot help with that topic and can only assist with currency-related queries. '
        'Do not attempt to answer unrelated questions or use tools for other purposes.'
    )

    FORMAT_INSTRUCTION = (
        'Set response status to input_required if the user needs to provide more information to complete the request.'
        'Set response status to error if there is an error while processing the request.'
        'Set response status to completed if the request is complete.'
    )

    def __init__(self):

        self.model = ChatOpenAI(
            proxy_model_name='gpt-4o-mini', 
            proxy_client=proxy_client,
            temperature=0            
        )
        self.tools = [get_exchange_rate]

        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=(self.FORMAT_INSTRUCTION, ResponseFormat),
        )

    async def stream(self, query, context_id) -> AsyncIterable[dict[str, Any]]:
        inputs = {'messages': [('user', query)]}
        config = {'configurable': {'thread_id': context_id}}

        for item in self.graph.stream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            if (
                isinstance(message, AIMessage)
                and message.tool_calls
                and len(message.tool_calls) > 0
            ):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Looking up the exchange rates...',
                }
            elif isinstance(message, ToolMessage):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Processing the exchange rates..',
                }

        yield self.get_agent_response(config)

    def get_agent_response(self, config):
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')
        if structured_response and isinstance(
            structured_response, ResponseFormat
        ):
            if structured_response.status == 'input_required':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            if structured_response.status == 'error':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            if structured_response.status == 'completed':
                return {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': structured_response.message,
                }

        return {
            'is_task_complete': False,
            'require_user_input': True,
            'content': (
                'We are unable to process your request at the moment. '
                'Please try again.'
            ),
        }

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']
```

It exposes a little baseline agent - able to convert a currency. Based on langgraph - one can get started from here.

```python
import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError

from agent import CurrencyAgent


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CurrencyAgentExecutor(AgentExecutor):
    """Currency Conversion AgentExecutor Example."""

    def __init__(self):
        self.agent = CurrencyAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task
        
        if not task:
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        
        # Log all properties of the context and task objects
        logger.info(f"Context properties: {vars(context)}")
        logger.info(f"Task properties: {vars(task)}")
        
        try:
            async for item in self.agent.stream(query, task.context_id):
                is_task_complete = item['is_task_complete']
                require_user_input = item['require_user_input']

                if not is_task_complete and not require_user_input:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(
                            item['content'],
                            task.context_id,
                            task.id,
                        ),
                    )
                elif require_user_input:
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(
                            item['content'],
                            task.context_id,
                            task.id,
                        ),
                        final=True,
                    )
                    break
                else:
                    await updater.add_artifact(
                        [Part(root=TextPart(text=item['content']))],
                        name='conversion_result',
                    )
                    await updater.complete()
                    break

        except Exception as e:
            logger.error(f'An error occurred while streaming the response: {e}')
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        return False

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise ServerError(error=UnsupportedOperationError())
```

In this code snippet, several key elements are visible. First, the a2a-sdk is heavily utilized, providing the base class for the AgentExecutor. This serves as the main interface for exposing an agent through the A2A SDK. Its primary method is execute, which receives a task from the A2A client, including context and task details, passes it to the agent, and processes the response. The SDK also handles sending intermittent updates and requesting user input as needed.

Finally, there is the transport layer. The app.py file exposes the Agent Card at the well-known endpoint and manages incoming requests. Here, the transport protocol can be chosen, with the default set to JSON-RPC.

```python
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
```

Again, this is mostly boilerplate code provided by the A2A SDK. We populate the Agent Card with the specific information for our use case and ensure that requests are handled appropriately. To do this, we instantiate the DefaultRequestHandler.

Finally, let's look at the files that enable deployment. The manifest.yaml facilitates deployment by providing configuration settings and the startup command:

```yaml
applications:
  - name: currency-agent
    memory: 512M
    disk_quota: 1G
    buildpacks:
      - python_buildpack
    env:
      # Add your SAP AI Core credentials here
      AICORE_AUTH_URL: "<your-auth-url>"
      AICORE_CLIENT_ID: "<your-client-id>"
      AICORE_CLIENT_SECRET: "<your-client-secret>"
      AICORE_RESOURCE_GROUP: "<your-resource-group>"
      AICORE_BASE_URL: "<your-base-url>"
    command: uvicorn app:app --host 0.0.0.0 --port ${PORT}
```

I am using the python_buildpack in conjunction with a specific Python version specified in the runtime.txt. Since we are utilizing the foundation models of the generative AI hub of AI Core, we also ensure to pass on our credentials via environment variables.

runtime.txt:

```
3.13.*
```

This is necessary because the dependencies only support Python versions greater than 3.12, while Cloud Foundry currently uses an earlier version by default.

```bash
cd app
cf push
```

With this structure in place, the agent can be deployed to Cloud Foundry. Alternatively, it can be hosted in any other environment of your choice. The resulting URL of your Python App will be needed in the Destination as well as in the Agent Card if you want to test it locally against the deployed version.

---

## 2. Building the Joule Pro-Code Capability

For this example, I prepared a minimal directory and code structure that you can utilize:

```
currencyagentcapability/
├── functions/
│   └── currencyagentfunction.yaml
├── scenarios/
│   └── currencyagentscenario.yaml
└── capability.sapdas.yaml
da.sapdas.yaml
```

Let's start with **capability.sapdas.yaml**. It describes the overall capability with some descriptions, defines the version of the design-time artifacts, and lets us configure the Destination mapping against the system alias.

```yaml
schema_version:  3.27.0   # be aware of the minimum version for agents

metadata:
  namespace: joule.ext    # very important to be in the "joule.ext" namespace for capabilities
  name: currency_agent_capability
  version: 1.0.0
  display_name: Currency Agent Capability
  description: Capability containing the currency agent

system_aliases:
  CURRENCY_AGENT:
    destination: CURRENCY_AGENT # this is referencing the destination name
```

**Note:** For our example, it is important to use version 3.27.0 onwards, since this is the minimum version for the Agent integration. In addition, we specify the namespace. Here we need to use the extension namespace joule.ext other namespaces will fail.

If you do not use the proper joule.ext namespace - you will run into the issue "User is not authorized to deploy sap capabilities . (error code: Tenant Administration Worker - 5014...)" this is because all other namespaces are considered to be "sap namespaces" - a bit like back in the day with Z.

At the bottom, we register a system alias and map it to a destination—both of which I call CURRENCY_AGENT. The destination will be named accordingly in the subsequent step in BTP.

Next, we introduce the scenario for our agent.

**currencyagentscenario.yaml**

```yaml
description: The Currency Agent supports converting between different currencies.
target:
  name: currency_agent_function
  type: function
```

It basically consists of the description and the target—in this case, the currencyagentfunction. Additionally, one could maintain parameters that would be collected by the Joule Orchestrator. For our particular case, for example, we could maintain a currency pair and an amount to convert. In addition, if your agent is handling multi-turn conversations, you might want to pass the conversation ID to it via the context.

Finally, the function:

**currencyagentfunction.yaml**

```yaml
action_groups:
  - actions:
      - type: agent-request   # This action type allows the agent to trigger an agent
        system_alias: CURRENCY_AGENT # The system alias is defined in the capability.sapdas.yaml file and points to the destination of the agent
        agent_type: remote # remote for code based agents
        result_variable: "apiResponse" # response of the agent - can be used in subsequent actions by referring to the variable name   
      - type: message
        message:
          type: text
          content: "<? apiResponse.body.artifacts[0].parts[0].text ?>"  # extracting textual response from the agent
```

In here, we define actions, and the most important one is the agent-request. It will invoke the Agent via the A2A integration. We specify the system alias, the type as remote, and which variable should hold the response.

**Note:** The response from the agent now needs to be "formatted" in this function. In this super minimalistic case, I just output the result body in a static message sent to the user.

---

## Understanding the Joule Agent Result Variable

When working with the **agent-request** action, the `result_variable` is the connection between the output of the agent and the formatting of the response to Joules Webclient. In that result variable we have the following:

### Key Components of the Response

* **Body:** The core container for the task data.
* **History:** A log of the conversation turns between the user and the agent.
* **Artifacts:** The final, structured answers or generated content.
* **Status:** The current state of the task (e.g., completed).

### Example

Below is a sample JSON payload returned by a Joule agent after a currency conversion request:

```json
{
  "headers": {},
  "body": {
    "kind": "task",
    "contextId": "98fa8d22-0e99-4efe-a1a9-fff535e7db9d",
    "history": [
      {
        "role": "user",
        "kind": "message",
        "parts": [{"kind": "text", "text": "Please convert 10 USD to euros"}],
        "messageId": "eb8b5afa-63cb-4cc5-9b24-38f85e782c95"
      },
      {
        "role": "agent",
        "kind": "message",
        "parts": [{"kind": "text", "text": "Looking up the exchange rates..."}]
      }
    ],
    "id": "f0d78896-0eab-472f-8a85-73050948c0a2",
    "artifacts": [
      {
        "name": "conversion_result",
        "parts": [
          {
            "kind": "text",
            "text": "10 USD is approximately 8.43 EUR based on the current exchange rate."
          }
        ],
        "artifactId": "b8d6c02b-1646-4676-969b-ca07f7df2af0"
      }
    ],
    "status": {
      "state": "completed",
      "timestamp": "2026-02-16T11:45:20.883269+00:00"
    }
  }
}
```

### Extracting Specific Information

Developers can use simple dot-notation scripting to drill down into this variable and extract specific data for the UI.

**Example:** To grab the final conversion text from the JSON above, you would navigate the path:
`apiResponse.body.artifacts[0].parts[0].text`

This allows you to bypass the background "thought" process or status updates and display only the exact information the user is looking for in a clean, conversational message.

---

## 3. Destination Creation

To bridge Joule with our remote Python agent, we need to establish a connection via the **SAP BTP Destination Service**. This follows the standard procedure for creating an HTTP destination within your BTP Subaccount.

In the BTP Cockpit, navigate to **Connectivity > Destinations** and create a new destination with the following details:

* **Name:** CURRENCY_AGENT (This must match the system alias we defined in our capability YAML).
* **Type:** HTTP
* **URL:** The base URL where your agent is hosted (e.g., your Cloud Foundry app URL).
* **Proxy Type:** Internet
* **Authentication:** For this demonstration and to keep things simple, I have selected NoAuthentication.

![Destination Create](../images/destination%20create.png)

The A2A integration handles the heavy lifting of discovery. When Joule triggers the agent request, it uses the URL provided in this destination to locate the well-known.json path (the discovery endpoint) of your agent.

From there, Joule retrieves the Agent Card, identifies the specific communication URL defined within that card (+ preferred protocol), and subsequently initiates A2A-compliant messaging to send tasks and receive responses from your agent.

---

## 4. Deploy the Joule Capability

Now that the Joule capability is built and the destination is configured to point toward our agent on Cloud Foundry, we can bring everything together. To do this, we will use the **Joule CLI** to deploy the capability to our instance.

### Deployment Workflow

The Joule CLI handles the lifecycle of your capability through three main phases:

1. **Authentication**: Use `joule login` to authenticate with the specific Joule instance where you want to deploy.
2. **Compilation**: The source files must be compiled into a `.daar` file (Design-time Artifact Archive), which is the deployable format Joule requires.
3. **Deployment**: The archive is uploaded and registered to the assistant.

Compile and deploy can be combined with the following command in the top level directory (not inside the capability folder):

```bash
joule deploy -c -n "<bot_name>"
```

* **-c (Compile)**: Tells the CLI to first package your YAML files into the .daar format.
* **-n (Name)**: By specifying a bot name, you are creating a standalone assistant for testing purposes.

### Sample Output:

```
> joule deploy -c  -n "currency_agent_test"
✔ Building designtime artifact (currency_agent_capability)
✔ Trigger compilation (C:\Github\joule-code-based-agent-sample\currency_agent_capability)
✔ Compiled (C:\Github\joule-code-based-agent-sample\currency_agent_capability)

Detailed logs:
WARNINGS:
Message:             DTA did not define an optional i18n folder
Path:
Category:            I18N
Severity:            LOW

✔ Downloaded runtime artifact (joule.ext_currency_agent_capability_1.0.0.daar)
✔ Building runtime artifact
  > joule.ext_currency_agent_capability_1.0.0.daar added to the RTA
✔ Triggering deployment (currency_agent_test)
✔ Your digital assistant (currency_agent_test) deployed successfully
```

That would have deployed my currency_agent_test assistant that I can then launch.

**Note:** Test Assistant vs. Production Update

By default, Joule uses the sap_digital_assistant for live enterprise scenarios. (Also when opening Joule with /joule) When you are first developing, using joule deploy -n allows you to test your logic in a isolated "sandbox" assistant without affecting the standard content. This is also where the da.sapdas.yaml file plays its role.

Once you are ready to move your capability into the main environment alongside SAP's standard content, you would typically use:

```bash
joule update "sap_digital_assistant" --capability-file capability.sapdas.yaml
```

This command pushes your capability into the existing sap_digital_assistant rather than creating a new standalone bot. Here you can execute the command local to your capability folder.

### Launching the Assistant

After a successful deployment, the CLI will provide a URL to access your new assistant. When you open this link, you will see the assistant name reflected in the URL path.

```
> joule launch "currency_agent_test"
✔ Launching: https://joule-pro-code-9r3t5r7a.eu10.sapdas.cloud.sap/webclient/standalone/currency_agent_test
```

From here, you can begin interacting with your custom LangGraph agent directly through the Joule interface.

---

## Conclusion

Finally, we can test our agent directly from within Joule. For this example, I am using a standalone Joule instance. With the necessary end-user role assigned to my user, I can open the Joule web client and ask Joule for a currency conversion:

![Joule Result](../images/joule%20result.png)

As you can see, the scenario is selected, the function is executed, and the agent request action delegates the call to my LangGraph agent deployed on Cloud Foundry. The response is generated there and sent back to Joule. Find the full code on [Github](https://github.com/fyx99/joule-pro-code-a2a).

Nice! This opens up plenty of possibilities for extending Joule with custom-built agents.

I hope you found this insightful. Since this blog covered only a very minimal example, stay tuned for additional posts. There are many topics to dive deeper into, such as authentication flows toward SAP systems via principal propagation, managing the agent context across multi-turn conversations, and response formats beyond simple text.
