# Ambient Expense Agent 🤖🚀

A premium, interactive web application featuring an intelligent customer support representative for a shipping company, powered by **Google ADK 2.0 (Agent Development Kit)** and **Gemini**.

The application uses a graph workflow to classify user queries, conditionally route them to specialized agent nodes, and visually present the **Agent Reasoning Flow** in a modern glassmorphic chat interface.

---

## ✨ Features

- **🧠 ADK 2.0 Graph Workflow**: Utilizes a stateful graph to guide queries through classification and routing.
- **🔍 Smart Query Classification**: A `classifier` node determines if a query is shipping-related (rates, tracking, delivery, returns) or unrelated.
- **📦 Shipping FAQ Representative**: A specialized node (`shipping_faq_agent`) that answers shipping questions. It features a playful, enthusiastic, emoji-packed response when discussing shipping rates, highlighting the **FREE SHIPPING for orders over $50** threshold.
- **⛔ Decline Representative**: A specialized node (`decline_agent`) that politely declines to answer unrelated queries, reinforcing its scope as a shipping agent.
- **🎨 Glassmorphic Chat UI**: A dark, premium user interface with glowing accents, smooth transitions, custom scrollbars, and Outfit/Plus Jakarta Sans typography.
- **⏱️ Live Timeline Visualization**: Displays the exact route executed by the workflow in real-time (e.g. `START ➔ classifier ➔ shipping_faq_agent`).
- **⚙️ Dual Execution Modes**:
  - **Live Mode**: Input a `GOOGLE_API_KEY` in the slide-out settings drawer to run live Gemini models.
  - **Simulation Mode**: Automatically falls back to a mocked runner to test the routing and interaction without credentials.

---

## 📁 Repository Structure

```text
├── customer-support-agent/     # ADK 2.0 Workflow Package
│   ├── agent.py                # Workflow definition, nodes (classifier, faq, decline), and edges
│   ├── __init__.py             # Exposes root workflow agent
│   ├── requirements.txt        # Workflow-specific dependencies
│   └── .env                    # Environment config (API Key)
├── customer_support_app.py     # Flask backend server driving the ADK workflow
├── requirements.txt            # Root application dependencies
├── .gitignore                  # Ignores virtual envs, python caches, and local secrets
├── templates/
│   └── customer_support.html   # Main chat application HTML template
└── static/
    ├── css/
    │   └── customer_support.css # Modern styling, neon glow, and layout animations
    └── js/
        └── customer_support.js  # Chat session management, settings drawer, and API handler
```

---

## 🚀 Getting Started

### Prerequisites
Make sure you have Python 3.10+ installed.

### 1. Installation
Clone the repository and install dependencies in a virtual environment:

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # On Windows

# Install requirements
pip install -r requirements.txt
```

### 2. Run the Application
Start the Flask application server:

```bash
python customer_support_app.py
```

*Note: The customer support application runs on port **5001** to prevent conflicts with other services.*

### 3. Open the Application
Open your browser and navigate to **[http://127.0.0.1:5001](http://127.0.0.1:5001)**.
