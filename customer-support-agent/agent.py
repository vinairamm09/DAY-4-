from google.adk import Agent, Workflow
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse


async def classify_router(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> LlmResponse:
    # Extract text from response
    parts = llm_response.content.parts if llm_response.content else []
    text = "".join([part.text for part in parts if part.text]).strip().upper()
    if "SHIPPING" in text:
        callback_context.actions.route = "SHIPPING"
    else:
        callback_context.actions.route = "UNRELATED"
    return llm_response


classifier = Agent(
    name="classifier",
    model="gemini-2.5-flash",
    instruction=(
        "You are a query classifier for a shipping company. "
        "Determine if the user's query is related to shipping (such as rates, tracking, delivery, returns, or general logistics) or unrelated. "
        "If it is related to shipping, reply with exactly the word 'SHIPPING'. "
        "If it is unrelated, reply with exactly the word 'UNRELATED'."
    ),
    after_model_callback=classify_router,
)

# Shipping FAQ agent to answer shipping-related questions
shipping_faq_agent = Agent(
    name="shipping_faq_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are a shipping company FAQ representative. "
        "Answer the user's shipping-related questions (about rates, tracking, delivery times, packaging, and returns) "
        "politely and clearly using shipping company context. "
        "When discussing shipping rates, be incredibly playful, energetic, and enthusiastic! "
        "Shower the user with fun emojis (like 🚀, 🎉, 🌟, 📦, 🥳, 💃). "
        "Always highlight that we offer absolutely **FREE SHIPPING for all orders over $50!**"
    ),
)

# Decline agent to politely decline answering unrelated questions
decline_agent = Agent(
    name="decline_agent",
    model="gemini-2.5-flash",
    instruction=(
        "Politely decline to answer the user's query. "
        "Explain that you are a specialized customer support representative for a shipping company "
        "and can only answer questions related to shipping (rates, tracking, delivery, returns)."
    ),
)

# Root workflow combining the nodes and routing edges
root_agent = Workflow(
    name="customer_support_workflow",
    edges=[
        ("START", classifier),
        (
            classifier,
            {
                "SHIPPING": shipping_faq_agent,
                "UNRELATED": decline_agent,
            },
        ),
    ],
)
