import contextlib
import os
import sys
from unittest.mock import MagicMock, patch
from flask import Flask, jsonify, render_template, request

# Add the agent folder to sys.path so we can import it
sys.path.append(os.path.join(os.path.dirname(__file__), "customer-support-agent"))

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import (
    Candidate,
    Content,
    FinishReason,
    GenerateContentResponse,
    Part,
)
from agent import root_agent

app = Flask(__name__)

# Shared in-memory session service for the web app
session_service = InMemorySessionService()

# Mock response generator for simulated runs
def mock_generate_content(model, contents, config=None):
    user_query = ""
    if isinstance(contents, list) and len(contents) > 0:
        parts = contents[-1].parts
        if parts:
            user_query = parts[0].text
    elif hasattr(contents, "parts"):
        user_query = contents.parts[0].text

    response_text = ""
    system_instruction = str(config.system_instruction if config else "")

    if "You are a query classifier" in system_instruction:
        # Classifier node logic
        q_lower = user_query.lower()
        keywords = ["ship", "rate", "track", "deliver", "return", "package", "cost", "price", "delay", "post", "send", "fee"]
        if any(kw in q_lower for kw in keywords):
            response_text = "SHIPPING"
        else:
            response_text = "UNRELATED"
    elif "shipping company FAQ representative" in system_instruction:
        # FAQ agent node logic
        q_lower = user_query.lower()
        if "rate" in q_lower or "cost" in q_lower or "price" in q_lower or "fee" in q_lower:
            response_text = "Oh boy, do we have some AMAZING news for you! 🌟✨ Standard shipping starts at just $5.99, and Express is $14.99! But wait... orders over $50 get absolutely **FREE SHIPPING!** 🚀📦🎉🥳 How awesome is that?! Let's get your package moving! 💃"
        elif "track" in q_lower or "status" in q_lower or "where" in q_lower:
            response_text = "You can track your shipment in real-time by entering your 12-digit tracking number on our website tracking page, or by contacting our support team with your order ID."
        elif "return" in q_lower or "refund" in q_lower:
            response_text = "We offer a 30-day return policy. You can print a prepaid return shipping label from our online portal. Once received, returns are processed within 3-5 business days."
        elif "deliver" in q_lower or "time" in q_lower or "delay" in q_lower or "schedule" in q_lower:
            response_text = "Standard delivery takes 3-5 business days, while Express takes 1-2 business days. Deliveries are made Monday through Saturday between 8:00 AM and 8:00 PM."
        else:
            response_text = "Hey there! We make shipping super fun and easy! 🚀 Standard shipping starts at only $5.99, and guess what? Shipping is absolutely **FREE on all orders over $50!** 🎉📦🥳 Let me know if you need help tracking your package, checking rates, or processing a return! 💃"
    elif "Politely decline to answer" in system_instruction:
        # Decline agent node logic
        response_text = "I apologize, but I am a customer support agent specialized only in shipping services (such as rates, tracking, delivery status, and returns). I cannot answer questions on other topics."
    else:
        response_text = "I can help you with shipping rates, tracking, deliveries, and returns. Please let me know what you need."

    return GenerateContentResponse(
        candidates=[
            Candidate(
                content=Content(
                    role="model",
                    parts=[Part(text=response_text)]
                ),
                finish_reason=FinishReason.STOP
            )
        ]
    )

@contextlib.contextmanager
def maybe_mock_client(use_mock: bool):
    if use_mock:
        mock_client = MagicMock()
        mock_aio_models = MagicMock()
        
        async def mock_async_generate_content(*args, **kwargs):
            return mock_generate_content(*args, **kwargs)
            
        mock_aio_models.generate_content = mock_async_generate_content
        mock_aio_models.generate_content_stream = mock_async_generate_content
        mock_client.aio.models = mock_aio_models
        
        with patch("google.genai.Client", return_value=mock_client):
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "mock_api_key"}):
                yield
    else:
        yield

@app.route("/")
def index():
    return render_template("customer_support.html")

@app.route("/api/chat", methods=["POST"])
async def chat():
    data = request.json or {}
    user_message = data.get("message", "")
    session_id = data.get("session_id", "default_session")
    api_key = data.get("api_key", "").strip()

    # Determine if we should run in mock mode
    # Run in mock mode if no custom API key is provided AND no ambient GOOGLE_API_KEY exists
    ambient_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    use_mock = not api_key and not ambient_key

    # Temp set key in environment if provided
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key

    try:
        with maybe_mock_client(use_mock):
            runner = Runner(
                agent=root_agent,
                app_name="customer-support-agent",
                session_service=session_service,
                auto_create_session=True,
            )

            new_message = Content(parts=[Part(text=user_message)])
            events = []
            
            async for event in runner.run_async(
                user_id="web_user",
                session_id=session_id,
                new_message=new_message,
            ):
                events.append(event)

            # Extract final text output
            final_text = ""
            for event in reversed(events):
                if event.content:
                    parts = event.content.parts if event.content.parts else []
                    final_text = "".join([p.text for p in parts if p.text])
                    break

            # Build list of executed nodes
            executed_nodes = [event.author for event in events if event.author]

            return jsonify({
                "response": final_text,
                "flow": executed_nodes,
                "is_mocked": use_mock
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temp key
        if api_key and "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

if __name__ == "__main__":
    # Run on port 5001 to avoid conflicts with BQ release hub app
    app.run(port=5001, debug=True)
