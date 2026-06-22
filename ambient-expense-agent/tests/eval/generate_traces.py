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

import os
import json
import base64
import unittest.mock
from pathlib import Path
import google.auth

# 1. Mock GCP credentials to avoid errors during local runs
google.auth.default = unittest.mock.MagicMock(
    return_value=(unittest.mock.MagicMock(), "dummy-project")
)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from vertexai._genai.types.common import EvalCase, EvaluationDataset
from expense_agent.agent import root_agent, detect_prompt_injection

def serialize_val(val):
    if hasattr(val, "model_dump"):
        return val.model_dump()
    elif hasattr(val, "dict"):
        return val.dict()
    return val

def main():
    print("Starting trace generation...")

    # Load dataset
    dataset_path = Path("tests/eval/datasets/basic-dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset_data = json.load(f)

    eval_cases = []
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name="expense_agent"
    )

    for case_data in dataset_data.get("eval_cases", []):
        case_id = case_data["eval_case_id"]
        prompt_text = case_data["prompt"]["parts"][0]["text"]
        print(f"Running case: {case_id}")

        # Parse payload
        payload = json.loads(prompt_text)

        # Create session
        session = session_service.create_session_sync(
            user_id="eval_user",
            app_name="expense_agent"
        )

        message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_text)]
        )

        # Initialize event list with the user prompt
        events_list = [
            {
                "author": "user",
                "content": {
                    "role": "user",
                    "parts": [{"text": prompt_text}]
                }
            }
        ]

        # Run first step
        events = list(
            runner.run(
                new_message=message,
                user_id="eval_user",
                session_id=session.id
            )
        )

        # Append generated events
        for event in events:
            author_name = getattr(event, "node_name", None) or event.author or "agent"
            if event.content and event.content.parts:
                text_val = "".join(p.text for p in event.content.parts if p.text)
                if text_val:
                    events_list.append({
                        "author": author_name,
                        "content": {
                            "role": event.content.role or "model",
                            "parts": [{"text": text_val}]
                        }
                    })
            if event.output is not None:
                events_list.append({
                    "author": author_name,
                    "content": {
                        "role": "model",
                        "parts": [{"text": f"[{author_name}] output: {json.dumps(serialize_val(event.output))}"}]
                    }
                })

        # Intercept human-in-the-loop approval step
        if events and events[-1].long_running_tool_ids and "decision" in events[-1].long_running_tool_ids:
            # Automate decision: reject injections, approve clean requests
            description = payload.get("description", "")
            is_injection = detect_prompt_injection(description)
            decision = "reject" if is_injection else "approve"

            print(f"  HITL Intercepted. Decision: {decision} (Is Injection: {is_injection})")

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

            # Resume running
            resume_events = list(
                runner.run(
                    new_message=resume_message,
                    user_id="eval_user",
                    session_id=session.id
                )
            )

            # Append resumed events
            for event in resume_events:
                author_name = getattr(event, "node_name", None) or event.author or "agent"
                if event.content and event.content.parts:
                    text_val = "".join(p.text for p in event.content.parts if p.text)
                    if text_val:
                        events_list.append({
                            "author": author_name,
                            "content": {
                                "role": event.content.role or "model",
                                "parts": [{"text": text_val}]
                            }
                        })
                if event.output is not None:
                    events_list.append({
                        "author": author_name,
                        "content": {
                            "role": "model",
                            "parts": [{"text": f"[{author_name}] output: {json.dumps(serialize_val(event.output))}"}]
                        }
                    })

        # Extract final response from events_list
        final_response_text = ""
        for ev in reversed(events_list):
            if ev["author"] != "user":
                parts = ev["content"]["parts"]
                text_val = "".join(p["text"] for p in parts if p.get("text"))
                if text_val:
                    final_response_text = text_val
                    break

        final_response = {
            "role": "model",
            "parts": [{"text": final_response_text}]
        }

        # Build EvalCase Pydantic model
        eval_case = EvalCase(
            eval_case_id=case_id,
            prompt=types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt_text)]
            ),
            responses=[{"response": final_response}],
            agent_data={
                "turns": [
                    {
                        "turn_index": 0,
                        "turn_id": "turn_0",
                        "events": events_list
                    }
                ]
            }
        )
        eval_cases.append(eval_case)

    # Save to artifacts/traces/generated_traces.json
    output_path = Path("artifacts/traces/generated_traces.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dataset = EvaluationDataset(eval_cases=eval_cases)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(dataset.model_dump_json(exclude_unset=True))

    print(f"Trace generation complete. Saved {len(eval_cases)} cases to {output_path}")

if __name__ == "__main__":
    main()
