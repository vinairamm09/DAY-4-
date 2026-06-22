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

import base64
import json
import os
import re
from collections.abc import AsyncGenerator, Generator
from typing import Any

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Workflow, node
from google.genai import types
from pydantic import BaseModel, Field

from expense_agent.config import AUTO_APPROVAL_THRESHOLD, MODEL_NAME

# Load environment variables
load_dotenv()


def scrub_description(text: str) -> tuple[str, list[str]]:
    redacted = []
    # SSN pattern: 3 digits, dash or space, 2 digits, dash or space, 4 digits
    ssn_pattern = r"\b\d{3}[- ]\d{2}[- ]\d{4}\b"
    # Credit Card patterns:
    # 1. 16-digit card with dashes/spaces: \b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b
    # 2. 15-digit Amex with dashes/spaces: \b\d{4}[- ]\d{6}[- ]\d{5}\b
    # 3. Raw 13-19 digit card numbers: \b\d{13,19}\b
    cc_pattern = r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b|\b\d{4}[- ]\d{6}[- ]\d{5}\b|\b\d{13,19}\b"

    scrubbed_text = text
    if re.search(ssn_pattern, text):
        scrubbed_text = re.sub(ssn_pattern, "[REDACTED SSN]", scrubbed_text)
        redacted.append("SSN")

    if re.search(cc_pattern, text):
        scrubbed_text = re.sub(cc_pattern, "[REDACTED CREDIT CARD]", scrubbed_text)
        redacted.append("Credit Card")

    return scrubbed_text, redacted


def detect_prompt_injection(text: str) -> bool:
    patterns = [
        r"ignore\s+(?:previous|all)\s+instructions",
        r"system\s+prompt",
        r"override\s+(?:rules|threshold|instructions|approval)",
        r"bypass\s+(?:rules|security|threshold|checks)",
        r"auto-approve",
        r"auto\s+approve",
        r"forget\s+(?:the|all)\s+rules",
        r"disregard\s+(?:previous|rules|instructions)",
        r"you\s+must\s+approve",
        r"new\s+rule",
        r"you\s+are\s+now",
        r"do\s+not\s+review",
    ]
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    return False


# Configure environment defaults for the Gemini client
if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "False").lower() == "true":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        import google.auth

        try:
            _, project_id = google.auth.default()
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        except Exception:
            pass
    if not os.environ.get("GOOGLE_CLOUD_LOCATION"):
        os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
else:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"


# --- Pydantic Models ---


class Expense(BaseModel):
    amount: float = Field(description="The total amount of the expense.")
    submitter: str = Field(description="The email or name of the submitter.")
    category: str = Field(
        description="The category of the expense (e.g., travel, meals, software)."
    )
    description: str = Field(description="Detailed description of the expense.")
    date: str = Field(description="The date of the expense.")


class RiskAssessment(BaseModel):
    risk_level: str = Field(description="Assessed risk level: Low, Medium, or High.")
    explanation: str = Field(
        description="Detailed reasoning for the risk level assessment."
    )


# --- Workflow Nodes ---


def parse_event(ctx: Context, node_input: Any) -> Event:
    """Parses incoming JSON/PubSub event under the 'data' key."""
    # Convert node_input to string or use it directly if it's a dict
    input_str = ""
    if isinstance(node_input, str):
        input_str = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        input_str = "".join(part.text for part in node_input.parts if part.text)

    # Load JSON dictionary
    data_dict = {}
    if input_str:
        try:
            data_dict = json.loads(input_str)
        except Exception:
            pass
    elif isinstance(node_input, dict):
        data_dict = node_input

    # PubSub base64 payload extraction
    data_payload = data_dict.get("data")
    expense_data = {}
    if data_payload:
        if isinstance(data_payload, str):
            try:
                # Try Base64 decoding
                decoded = base64.b64decode(data_payload).decode("utf-8")
                expense_data = json.loads(decoded)
            except Exception:
                # Fallback to direct JSON loading
                try:
                    expense_data = json.loads(data_payload)
                except Exception:
                    pass
        elif isinstance(data_payload, dict):
            expense_data = data_payload
    else:
        # Fallback to parsing root dictionary directly (e.g. playground testing)
        expense_data = data_dict

    # Extract required fields with safe fallbacks
    try:
        amount = float(expense_data.get("amount", 0.0))
    except Exception:
        amount = 0.0

    expense = Expense(
        amount=amount,
        submitter=str(expense_data.get("submitter", "Unknown")),
        category=str(expense_data.get("category", "General")),
        description=str(expense_data.get("description", "")),
        date=str(expense_data.get("date", "")),
    )

    # Route based on threshold
    if expense.amount < AUTO_APPROVAL_THRESHOLD:
        route = "auto_approve"
    else:
        route = "security_check"

    return Event(output=expense, route=route, state={"expense": expense.model_dump()})


def auto_approve(ctx: Context, node_input: Expense) -> Generator[Event, None, None]:
    """Auto-approves expenses under $100."""
    expense = node_input
    outcome = {
        "status": "APPROVED",
        "reason": f"Under ${AUTO_APPROVAL_THRESHOLD:.2f} threshold (auto-approved).",
        "amount": expense.amount,
        "submitter": expense.submitter,
        "category": expense.category,
        "description": expense.description,
        "date": expense.date,
    }

    yield Event(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=f"✅ **Auto-Approved**: Expense of **${expense.amount:.2f}** by **{expense.submitter}** is under the threshold."
                )
            ],
        )
    )
    yield Event(output=outcome)


def security_checkpoint(ctx: Context, node_input: Expense) -> Event:
    """Scrubs personal data from the description and defends against prompt injection."""
    expense = node_input
    description = expense.description
    state_delta = {}

    # 1. Scrub personal data
    scrubbed_desc, redacted_categories = scrub_description(description)
    if redacted_categories:
        expense.description = scrubbed_desc
        state_delta["expense"] = expense.model_dump()
        state_delta["redacted_categories"] = redacted_categories

    # 2. Defend against prompt injection
    if detect_prompt_injection(description):
        state_delta["security_event"] = True
        route = "security_flagged"
    else:
        route = "llm_review"

    return Event(output=expense, route=route, state=state_delta)


# LLM Node for risk review
llm_reviewer = LlmAgent(
    name="llm_reviewer",
    model=MODEL_NAME,
    instruction=(
        "You are a professional risk compliance assistant. Review the provided expense report details. "
        "Determine the risk level (Low, Medium, High) based on factors such as suspicious descriptions, "
        "misaligned categories, or unusually high values, and explain your reasoning clearly."
    ),
    output_schema=RiskAssessment,
    output_key="risk_assessment",
)


@node(rerun_on_resume=True)
async def human_approval(ctx: Context, node_input: Any) -> AsyncGenerator[Event, None]:
    """Asks for human approval (HITL) for expenses >= $100."""
    expense_dict = ctx.state.get("expense", {})

    # Extract risk assessment safely whether it is a dict or a Pydantic model
    if ctx.state.get("security_event"):
        risk_level = "High (Security Alert)"
        explanation = "LLM review bypassed: Prompt injection attempt detected."
    elif isinstance(node_input, dict):
        risk_level = node_input.get("risk_level", "Unknown")
        explanation = node_input.get("explanation", "")
    elif node_input is not None and hasattr(node_input, "risk_level"):
        risk_level = getattr(node_input, "risk_level", "Unknown")
        explanation = getattr(node_input, "explanation", "")
    else:
        # Fallback to session state if node_input is None
        risk_state = ctx.state.get("risk_assessment", {})
        risk_level = risk_state.get("risk_level", "Unknown")
        explanation = risk_state.get("explanation", "")

    # Yield RequestInput if human decision is not yet in resume_inputs
    if not ctx.resume_inputs or "decision" not in ctx.resume_inputs:
        msg_parts = []
        if ctx.state.get("security_event"):
            msg_parts.append(
                "🚨 **SECURITY ALERT: Potential Prompt Injection Detected** 🚨\n"
            )
        else:
            msg_parts.append("⚠️ **Pending Expense Approval ($100+)**\n")

        msg_parts.append(
            f"• **Submitter:** {expense_dict.get('submitter')}\n"
            f"• **Amount:** ${expense_dict.get('amount')}\n"
            f"• **Category:** {expense_dict.get('category')}\n"
            f"• **Description:** {expense_dict.get('description')}\n"
            f"• **Date:** {expense_dict.get('date')}\n"
        )

        redacted = ctx.state.get("redacted_categories", [])
        if redacted:
            msg_parts.append(f"• **Redacted Categories:** {', '.join(redacted)}\n")

        msg_parts.append(
            f"\n**LLM Risk Assessment:**\n"
            f"• **Risk Level:** {risk_level}\n"
            f"• **Explanation:** {explanation}\n\n"
            f"Type 'approve' or 'reject' to make a decision."
        )

        msg = "".join(msg_parts)
        yield RequestInput(interrupt_id="decision", message=msg)
        return

    # Once resumed, process human decision
    raw_decision = ctx.resume_inputs["decision"]
    if isinstance(raw_decision, dict):
        decision = str(
            raw_decision.get("decision") or raw_decision.get("response") or raw_decision
        )
    else:
        decision = str(raw_decision)
    is_approved = "approve" in decision.lower() or "yes" in decision.lower()

    yield Event(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=f"👤 **Human Decision**: {'Approved' if is_approved else 'Rejected'} ({decision})"
                )
            ],
        )
    )

    outcome = {
        "status": "APPROVED" if is_approved else "REJECTED",
        "reason": f"Human decision: {decision}",
        "amount": expense_dict.get("amount"),
        "submitter": expense_dict.get("submitter"),
        "category": expense_dict.get("category"),
        "description": expense_dict.get("description"),
        "date": expense_dict.get("date"),
        "risk_level": risk_level,
        "risk_explanation": explanation,
    }
    if ctx.state.get("security_event"):
        outcome["security_event"] = True
    redacted = ctx.state.get("redacted_categories", [])
    if redacted:
        outcome["redacted_categories"] = redacted

    yield Event(output=outcome)


def record_outcome(ctx: Context, node_input: dict) -> Generator[Event, None, None]:
    """Records the final decision outcome."""
    outcome = node_input
    status = outcome.get("status")
    amount = outcome.get("amount", 0.0)
    submitter = outcome.get("submitter", "Unknown")
    reason = outcome.get("reason", "")

    msg = f"🏁 **Workflow Concluded**: **{status}** for **${amount:.2f}** submitted by **{submitter}**.\nDetails: {reason}"

    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)])
    )
    yield Event(output=outcome, state={"outcome": outcome})


# --- Graph Wiring ---

root_agent = Workflow(
    name="expense_approval_workflow",
    edges=[
        (START, parse_event),
        (
            parse_event,
            {"auto_approve": auto_approve, "security_check": security_checkpoint},
        ),
        (
            security_checkpoint,
            {"llm_review": llm_reviewer, "security_flagged": human_approval},
        ),
        (llm_reviewer, human_approval),
        (auto_approve, record_outcome),
        (human_approval, record_outcome),
    ],
)

app = App(
    root_agent=root_agent,
    name="expense_agent",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
