# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from expense_agent.agent import root_agent

# 1. Telemetry Constraints: Disable OpenTelemetry exporting to cloud
os.environ["ADK_TRACE_TO_CLOUD"] = "False"
os.environ["ADK_OTEL_TO_CLOUD"] = "False"
os.environ["GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"] = "False"

# 2. Logging Setup: Standard Python logging for console logs
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ambient_expense_agent")

app = FastAPI(title="Ambient Expense Approval Web Service")

# Setup ADK Runner with InMemorySessionService
session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    session_service=session_service,
    app_name="expense_agent",
)


@app.post("/")
@app.post("/apps/expense_agent/trigger/pubsub")
async def handle_pubsub_trigger(request: Request):
    """POST endpoint to accept Pub/Sub push subscription messages and trigger the workflow."""
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse incoming JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    message = body.get("message")
    if not message:
        logger.error("Incoming Pub/Sub payload is missing the 'message' field")
        raise HTTPException(status_code=400, detail="Missing message field")

    message_id = message.get("messageId", "unknown-msg-id")

    # Gotcha handling: Normalize the fully-qualified subscription path to a short name
    subscription_path = body.get("subscription", "")
    subscription_name = (
        subscription_path.split("/")[-1]
        if subscription_path
        else "default-subscription"
    )

    # Keep session records readable using the normalized subscription name and message ID
    session_id = f"{subscription_name}-{message_id}"
    user_id = subscription_name

    logger.info(
        f"Processing Pub/Sub event {message_id} from subscription '{subscription_name}' in session '{session_id}'"
    )

    # Extract the inner message for the ADK workflow to run
    pubsub_msg = message

    msg_content = types.Content(
        role="user", parts=[types.Part.from_text(text=json.dumps(pubsub_msg))]
    )

    # Ensure the session is initialized in the session service
    try:
        session_service.create_session_sync(
            app_name="expense_agent",
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        pass

    try:
        events = []
        for event in runner.run(
            new_message=msg_content,
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)
            if event.output:
                logger.info(f"Node execution output: {event.output}")
            if event.content and event.content.parts:
                text_content = "".join(
                    part.text for part in event.content.parts if part.text
                )
                logger.info(f"Node text output: {text_content}")

        # If workflow has active interrupts, return its suspended state
        if events and events[-1].long_running_tool_ids:
            logger.info("Workflow suspended at human approval. Interrupt ID: decision")
            return {
                "status": "SUSPENDED",
                "message_id": message_id,
                "session_id": session_id,
                "interrupt_id": "decision",
                "message": "Workflow suspended for human-in-the-loop decision",
            }

        # Retrieve the final completed outcome
        final_output = None
        for event in reversed(events):
            if event.output:
                final_output = event.output
                break

        return {
            "status": "COMPLETED",
            "message_id": message_id,
            "session_id": session_id,
            "output": final_output,
        }

    except Exception as e:
        logger.exception(f"Error occurred during workflow execution: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/sessions")
@app.get("/apps/expense_agent/sessions")
async def list_sessions():
    """Endpoint to inspect active session statuses and states."""
    sessions = session_service.list_sessions_sync(app_name="expense_agent")
    res = []
    for s in sessions.sessions:
        res.append(
            {
                "session_id": s.id,
                "state": s.state,
                "is_suspended": "outcome" not in s.state,
            }
        )
    return res


@app.post("/resume/{session_id}")
@app.post("/apps/expense_agent/resume/{session_id}")
async def resume_session(session_id: str, decision: str):
    """Endpoint to resume a suspended HITL session with a human decision ('approve' or 'reject')."""
    resume_message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name="adk_request_input",
                    id="decision",
                    response={"decision": decision},
                )
            )
        ],
    )

    user_id = (
        session_id.rsplit("-", 1)[0] if "-" in session_id else "default-subscription"
    )

    try:
        events = []
        for event in runner.run(
            new_message=resume_message,
            user_id=user_id,
            session_id=session_id,
        ):
            events.append(event)
            if event.output:
                logger.info(f"Resume Node output: {event.output}")

        final_output = None
        for event in reversed(events):
            if event.output:
                final_output = event.output
                break

        return {
            "status": "COMPLETED",
            "session_id": session_id,
            "output": final_output,
        }
    except Exception as e:
        logger.exception(f"Failed to resume session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    uvicorn.run(
        "expense_agent.agent_runtime_app:app", host="127.0.0.1", port=8080, reload=True
    )
