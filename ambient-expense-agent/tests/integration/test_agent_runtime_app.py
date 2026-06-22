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

import unittest.mock

import google.auth
from fastapi.testclient import TestClient

# Mock google.auth.default to prevent credentials error during test execution
google.auth.default = unittest.mock.MagicMock(
    return_value=(unittest.mock.MagicMock(), "dummy-project")
)

from expense_agent.agent_runtime_app import app  # noqa: E402

client = TestClient(app)


def test_pubsub_trigger_auto_approve() -> None:
    """Tests the Pub/Sub trigger endpoint with an expense under $100 (auto-approve)."""
    payload = {
        "message": {
            "data": "eyJhbW91bnQiOiA0NS41MCwgInN1Ym1pdHRlciI6ICJhbGljZUBjb21wYW55LmNvbSIsICJjYXRlZ29yeSI6ICJtZWFscyIsICJkZXNjcmlwdGlvbiI6ICJMdW5jaCBtZWV0aW5nIiwgImRhdGUiOiAiMjAyNi0wNi0yMiJ9",
            "messageId": "msg123",
        },
        "subscription": "projects/test-project/subscriptions/test-sub",
    }

    response = client.post("/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["message_id"] == "msg123"
    assert data["session_id"] == "test-sub-msg123"
    assert data["output"]["status"] == "APPROVED"
    assert "auto-approved" in data["output"]["reason"]


def test_pubsub_trigger_suspended_and_resume() -> None:
    """Tests the Pub/Sub trigger endpoint with an expense >= $100, which suspends and is then resumed."""
    # 1. Trigger the workflow (which should suspend at human review)
    payload = {
        "message": {
            "data": "eyJhbW91bnQiOiAxNTAuMCwgInN1Ym1pdHRlciI6ICJib2JAY29tcGFueS5jb20iLCAiY2F0ZWdvcnkiOiAic29mdHdhcmUiLCAiZGVzY3JpcHRpb24iOiAiSURFIExpY2Vuc2UiLCAiZGF0ZSI6ICIyMDI2LTA2LTIyIn0=",
            "messageId": "msg456",
        },
        "subscription": "projects/test-project/subscriptions/test-sub",
    }

    response = client.post("/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUSPENDED"
    assert data["message_id"] == "msg456"
    assert data["session_id"] == "test-sub-msg456"
    assert data["interrupt_id"] == "decision"

    # 2. Check the sessions list endpoint
    sessions_response = client.get("/sessions")
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert any(
        s["session_id"] == "test-sub-msg456" and s["is_suspended"] for s in sessions
    )

    # 3. Resume the session with approval
    resume_response = client.post("/resume/test-sub-msg456?decision=approve")
    assert resume_response.status_code == 200
    resume_data = resume_response.json()
    assert resume_data["status"] == "COMPLETED"
    assert resume_data["session_id"] == "test-sub-msg456"
    assert resume_data["output"]["status"] == "APPROVED"
    assert "Human decision" in resume_data["output"]["reason"]
