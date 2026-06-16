import os

from collections.abc import AsyncIterable
from typing import Any, Literal, Optional

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
from gen_ai_hub.proxy.core.proxy_clients import get_proxy_client

from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from s4_client import call_business_partner_api

proxy_client = get_proxy_client('gen-ai-hub')


memory = MemorySaver()


@tool
def get_business_partners(
    top: int = 10,
    filter_expr: str | None = None,
    select: str | None = None,
    expand: str | None = None,
    orderby: str | None = None,
    config: RunnableConfig = None,
) -> dict:
    """Query business partners from S/4HANA on behalf of the logged-in user.

    Uses OData v2 query options against API_BUSINESS_PARTNER/A_BusinessPartner.
    The current user identity is propagated via SAML Bearer through the BTP
    destination service — only data the user is authorized to see is returned.

    Args:
        top: Max number of rows ($top). Default 10. Cap around 100 for sanity.
        filter_expr: OData $filter expression.
            Examples:
              - "BusinessPartnerCategory eq '1'"            (1 = person, 2 = organization)
              - "startswith(BusinessPartnerName,'Inland')"
              - "CreationDate ge datetime'2023-01-01T00:00:00'"
              - "Country eq 'DE'"
              - "Industry eq 'Z001' and Country eq 'DE'"
        select: OData $select. Comma-separated fields. Defaults to a sensible set.
            Available fields include: BusinessPartner, BusinessPartnerName,
            BusinessPartnerCategory, BusinessPartnerGrouping, CreationDate,
            Industry, FirstName, LastName, OrganizationBPName1.
        expand: OData $expand. Use to pull related entities, e.g.
            "to_BusinessPartnerAddress" for postal addresses.
        orderby: OData $orderby. Examples: "BusinessPartnerName asc",
            "CreationDate desc".
    """
    jwt = (config or {}).get("configurable", {}).get("jwt")
    if not jwt:
        return {"error": "No user JWT in tool context."}
    try:
        return {
            "business_partners": call_business_partner_api(
                jwt,
                top=top,
                filter_expr=filter_expr,
                select=select,
                expand=expand,
                orderby=orderby,
            )
        }
    except Exception as e:
        return {"error": f"S/4 call failed: {e}"}


class ResponseFormat(BaseModel):
    """Respond to the user in this format."""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str


class BusinessPartnerAgent:
    """BusinessPartnerAgent - looks up business partners from S/4HANA on behalf of the logged-in user."""

    SYSTEM_INSTRUCTION = (
        'You are a specialized assistant for S/4HANA business partner lookups. '
        "Use the 'get_business_partners' tool to query the S/4 Business Partner API. "
        'You can use OData $filter expressions to narrow results — e.g. by country, '
        "category (1=person, 2=organization), industry, name prefix, or creation date. "
        'You can use $orderby to sort, $expand for related entities like addresses, '
        'and $select to pick specific fields. '
        'For complex questions, break them into multiple tool calls. '
        'Always answer in well-formatted markdown (tables for tabular data). '
        'If the user asks something that has nothing to do with business partners, politely decline.'
        '\n\n'
        'Set response status to input_required if the user needs to provide more information to complete the request. '
        'Set response status to error if there is an error while processing the request. '
        'Set response status to completed if the request is complete.'
    )

    def __init__(self):

        self.model = ChatOpenAI(
            proxy_model_name='gpt-4o-mini',
            proxy_client=proxy_client,
            temperature=0,
        )
        self.tools = [get_business_partners]

        self.graph = create_agent(
            model=self.model,
            tools=self.tools,
            checkpointer=memory,
            system_prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

    async def stream(
        self,
        query,
        context_id,
        user_jwt: Optional[str] = None,
    ) -> AsyncIterable[dict[str, Any]]:
        inputs = {'messages': [('user', query)]}
        config = {
            'configurable': {
                'thread_id': context_id,
                'jwt': user_jwt,   # picked up by every tool that declares `config: RunnableConfig`
            }
        }

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
                    'content': 'Looking up business partners...',
                }
            elif isinstance(message, ToolMessage):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Processing the business partner data..',
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
