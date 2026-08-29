import asyncio
import os

from control_schemas import RuntimeExecutionRequest
from control_sdk import (
    ActionBlockedError,
    ControlRuntimeClient,
    ControlledExecution,
)


async def run_demo() -> None:
    api_key = os.environ.get("CONTROL_API_KEY")
    if not api_key:
        raise SystemExit("Set CONTROL_API_KEY to a local project API key")

    base_url = os.environ.get("CONTROL_API_URL", "http://127.0.0.1:8000")
    async with ControlRuntimeClient(base_url=base_url, api_key=api_key) as client:
        execution = await ControlledExecution.start(
            client,
            RuntimeExecutionRequest(
                task="Demonstrate automatic no-progress loop blocking",
                provider="mock",
                model="mock-model",
                application_slug="research-agent",
                repeat_threshold=3,
            ),
        )
        print(f"Execution: {execution.execution_id}")

        try:
            for attempt in range(1, 7):
                result = await execution.run_tool(
                    name="search",
                    arguments={"query": "Indian watershed monitoring"},
                    handler=lambda: {"items": [], "source": "local-demo"},
                    progress=False,
                    summary="Search returned no useful results",
                )
                print(f"Attempt {attempt}: allowed, items={len(result['items'])}")
        except ActionBlockedError as error:
            print("Next tool call: blocked before execution")
            print(f"Reason: {error}")
            print(f"Checkpoint: {error.checkpoint_id}")


if __name__ == "__main__":
    asyncio.run(run_demo())
