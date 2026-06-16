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

from agent import BusinessPartnerAgent


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BusinessPartnerAgentExecutor(AgentExecutor):
    """Business Partner AgentExecutor — propagates the user identity to S/4 via SAML Bearer."""

    def __init__(self):
        self.agent = BusinessPartnerAgent()

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
        logger.debug(f"Context properties: {vars(context)}")
        logger.debug(f"Task properties: {vars(task)}")

        # Pull the IAS user token out of the A2A RequestContext.
        # The token comes straight from the Authorization header of the Joule call
        # and is exposed at context._call_context.state["headers"]["authorization"].
        user_jwt = None
        try:
            headers = context._call_context.state.get("headers", {})
            auth = headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                user_jwt = auth[len("bearer "):]
        except AttributeError:
            logger.warning("No call_context on RequestContext - running without user token")

        try:
            async for item in self.agent.stream(query, task.context_id, user_jwt=user_jwt):
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
                        name='business_partner_result',
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