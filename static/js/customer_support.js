document.addEventListener("DOMContentLoaded", () => {
    // Generate a unique session ID for this load
    const sessionId = "sess_" + Math.random().toString(36).substring(2, 15);
    
    // DOM Elements
    const chatHistory = document.getElementById("chatHistory");
    const chatInput = document.getElementById("chatInput");
    const chatForm = document.getElementById("chatForm");
    const btnSettings = document.getElementById("btnSettings");
    const btnCloseSettings = document.getElementById("btnCloseSettings");
    const settingsOverlay = document.getElementById("settingsOverlay");
    const btnSaveSettings = document.getElementById("btnSaveSettings");
    const apiKeyInput = document.getElementById("apiKeyInput");
    const modeBadge = document.getElementById("modeBadge");
    
    // Timeline steps
    const stepClassifier = document.getElementById("stepClassifier");
    const stepFaq = document.getElementById("stepFaq");
    const stepDecline = document.getElementById("stepDecline");
    
    // Load existing API key if present
    let apiKey = localStorage.getItem("google_adk_api_key") || "";
    if (apiKey) {
        apiKeyInput.value = apiKey;
        updateModeBadge(true);
    } else {
        updateModeBadge(false);
    }
    
    // Auto scroll chat window
    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
    
    // Update Mode Badge based on API Key presence
    function updateModeBadge(hasKey) {
        if (hasKey) {
            modeBadge.textContent = "Live Mode";
            modeBadge.className = "mode-badge live";
        } else {
            modeBadge.textContent = "Simulation Mode";
            modeBadge.className = "mode-badge mock";
        }
    }
    
    // Open/Close Settings
    btnSettings.addEventListener("click", () => {
        settingsOverlay.classList.add("open");
    });
    
    btnCloseSettings.addEventListener("click", () => {
        settingsOverlay.classList.remove("open");
    });
    
    settingsOverlay.addEventListener("click", (e) => {
        if (e.target === settingsOverlay) {
            settingsOverlay.classList.remove("open");
        }
    });
    
    // Save Settings
    btnSaveSettings.addEventListener("click", () => {
        apiKey = apiKeyInput.value.trim();
        if (apiKey) {
            localStorage.setItem("google_adk_api_key", apiKey);
            updateModeBadge(true);
        } else {
            localStorage.removeItem("google_adk_api_key");
            updateModeBadge(false);
        }
        settingsOverlay.classList.remove("open");
        
        // Append a system message indicating state change
        appendSystemMessage(apiKey ? "API Key updated. Switched to Live Gemini mode." : "API Key cleared. Switched to Graph Simulation mode.");
    });
    
    // Append messages
    function appendMessage(sender, text) {
        const messageDiv = document.createElement("div");
        messageDiv.className = `message ${sender}`;
        
        const avatar = document.createElement("div");
        avatar.className = "avatar";
        avatar.textContent = sender === "user" ? "👤" : "🤖";
        
        const content = document.createElement("div");
        content.className = "message-content";
        content.textContent = text;
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);
        
        chatHistory.appendChild(messageDiv);
        scrollToBottom();
    }
    
    function appendSystemMessage(text) {
        const systemDiv = document.createElement("div");
        systemDiv.style.alignSelf = "center";
        systemDiv.style.fontSize = "0.75rem";
        systemDiv.style.color = "var(--text-muted)";
        systemDiv.style.background = "rgba(255, 255, 255, 0.02)";
        systemDiv.style.border = "1px solid var(--panel-border)";
        systemDiv.style.padding = "4px 12px";
        systemDiv.style.borderRadius = "20px";
        systemDiv.style.margin = "10px 0";
        systemDiv.textContent = text;
        
        chatHistory.appendChild(systemDiv);
        scrollToBottom();
    }
    
    // Show/Hide typing indicator
    let typingIndicator = null;
    function showTypingIndicator() {
        if (typingIndicator) return;
        
        typingIndicator = document.createElement("div");
        typingIndicator.className = "message agent";
        
        const avatar = document.createElement("div");
        avatar.className = "avatar";
        avatar.textContent = "🤖";
        
        const content = document.createElement("div");
        content.className = "message-content";
        
        const indicator = document.createElement("div");
        indicator.className = "typing-indicator";
        
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement("div");
            dot.className = "typing-dot";
            indicator.appendChild(dot);
        }
        
        content.appendChild(indicator);
        typingIndicator.appendChild(avatar);
        typingIndicator.appendChild(content);
        
        chatHistory.appendChild(typingIndicator);
        scrollToBottom();
    }
    
    function removeTypingIndicator() {
        if (typingIndicator) {
            typingIndicator.remove();
            typingIndicator = null;
        }
    }
    
    // Update Graph Timeline Animation
    function resetTimeline() {
        const steps = [stepClassifier, stepFaq, stepDecline];
        steps.forEach(step => {
            step.className = "timeline-item";
        });
    }
    
    async function animateTimeline(flow) {
        resetTimeline();
        
        if (!flow || flow.length === 0) return;
        
        // 1. Classifier start
        if (flow.includes("classifier")) {
            stepClassifier.className = "timeline-item active";
            await sleep(800);
            stepClassifier.className = "timeline-item completed";
        }
        
        // 2. Shipping FAQ or Decline
        if (flow.includes("shipping_faq_agent")) {
            stepFaq.className = "timeline-item active";
            await sleep(800);
            stepFaq.className = "timeline-item completed";
        } else if (flow.includes("decline_agent")) {
            stepDecline.className = "timeline-item active";
            await sleep(800);
            stepDecline.className = "timeline-item completed";
        }
    }
    
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    // Chat Submit Handler
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const messageText = chatInput.value.trim();
        if (!messageText) return;
        
        // Append user message
        appendMessage("user", messageText);
        chatInput.value = "";
        
        // Show typing indicator
        showTypingIndicator();
        
        // Initialize timeline classifier step
        stepClassifier.className = "timeline-item active";
        
        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: messageText,
                    session_id: sessionId,
                    api_key: apiKey
                })
            });
            
            if (!response.ok) {
                throw new Error("Failed to communicate with agent.");
            }
            
            const data = await response.json();
            
            // Animate workflow flow
            await animateTimeline(data.flow || []);
            
            // Remove typing indicator & append agent response
            removeTypingIndicator();
            appendMessage("agent", data.response || "No response received.");
            
            // Update live/mock status indicator badge
            updateModeBadge(!data.is_mocked);
            
        } catch (error) {
            console.error("Error:", error);
            removeTypingIndicator();
            resetTimeline();
            appendMessage("agent", "Sorry, an error occurred while processing your request. Please check your console or server log.");
        }
    });
    
    // Initial welcome message
    appendMessage("agent", "Hello! I am a shipping customer support representative. I can help you with shipping rates, tracking details, delivery schedules, and return policies. What can I assist you with today?");
});
