"""Async A2A executor for the currency agent.

Boilerplate is intentionally thin here — the heavy lifting lives in two
neighbours: `agent.py` produces the stream of intermediate + final results,
and `joule_client.py` handles the destination-service exchange and the
JSON-RPC envelopes for the callback. This file is just the glue:

  1. Pull the user JWT and correlation headers off the inbound request
     (PP-style — `context._call_context.state["headers"]`).
  2. Enqueue the initial task event so the SDK can return a fast HTTP 200
     to Joule.
  3. Schedule the long-running work as a background asyncio task.
  4. In the background, iterate `agent.stream(...)` and push each step out
     via `joule_client` — `working` for intermediate steps, `completed` /
     `input-required` for the terminal one.
"""
import asyncio
import logging

import httpx
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    InternalError,
    InvalidParamsError,
    UnsupportedOperationError,
)
from a2a.utils import new_task
from a2a.utils.errors import ServerError

import joule_client
from agent import CurrencyAgent


logger = logging.getLogger(__name__)


def _extract_request_state(context: RequestContext) -> tuple[str, str, str]:
    """Pull user JWT + Joule correlation headers out of the A2A RequestContext.

    Same shape as `a2a_principal_propagation/app/agent_executor.py`: Joule
    forwards everything we need on `context._call_context.state["headers"]`.
    """
    headers = context._call_context.state.get("headers", {}) if context._call_context else {}
    auth = headers.get("authorization", "")
    user_jwt = auth[len("Bearer "):] if auth.lower().startswith("bearer ") else ""
    return (
        user_jwt,
        headers.get("conversationid", ""),
        headers.get("x-correlationid", ""),
    )


class CurrencyAgentExecutor(AgentExecutor):
    """Currency Conversion AgentExecutor — async push notifications via Joule callback."""

    def __init__(self):
        self.agent = CurrencyAgent()
        # Track in-flight background tasks so they aren't garbage-collected
        # before they finish pushing the final result.
        self._background_tasks: set[asyncio.Task] = set()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        if self._validate_request(context):
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task
        if not task:
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)

        user_jwt, conversation_id, correlation_id = _extract_request_state(context)
        if not user_jwt:
            logger.warning("No user token on RequestContext — async callback will fail")

        # Decouple the long-running work from the inbound HTTP request so the
        # SDK can return 200 to Joule immediately. Heartbeats and the final
        # result come back through the async callback URL.
        bg = asyncio.create_task(
            self._push_results(task, query, user_jwt, conversation_id, correlation_id),
            name=f"async-task-{task.id}",
        )
        self._background_tasks.add(bg)
        bg.add_done_callback(self._background_tasks.discard)

    async def _push_results(
        self,
        task,
        query: str,
        user_jwt: str,
        conversation_id: str,
        correlation_id: str,
    ) -> None:
        """Iterate the agent's stream and push each step to Joule's callback."""
        async with httpx.AsyncClient() as http:
            try:
                async for item in self.agent.stream(query, task.context_id):
                    if item['is_task_complete']:
                        body = joule_client.completed_envelope(
                            task.id, task.context_id, correlation_id, item['content'],
                        )
                    elif item['require_user_input']:
                        body = joule_client.input_required_envelope(
                            task.id, task.context_id, correlation_id, item['content'],
                        )
                    else:
                        body = joule_client.working_envelope(
                            task.id, task.context_id, correlation_id, item['content'],
                        )

                    resp = await joule_client.post_callback(
                        http=http,
                        user_jwt=user_jwt,
                        conversation_id=conversation_id,
                        correlation_id=correlation_id,
                        body=body,
                    )
                    resp.raise_for_status()
                    logger.info(
                        "Pushed %s for task_id=%s",
                        body["result"]["status"]["state"], task.id,
                    )
            except Exception:
                logger.exception("Background task failed for task_id=%s", task.id)

    def _validate_request(self, context: RequestContext) -> bool:
        return False

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())
