# ⬡ NexusLocal

> **Tired of hit-the-wall rate limits and "Wait 3 Hours" screens on Claude and ChatGPT?**  
> NexusLocal is a local-first chat interface that aggregates and orchestrates multiple free-tier LLM APIs (Gemini, Groq, SambaNova, OpenRouter, and more) so you can keep coding and chatting without interruptions.

---

## 🧬 Why NexusLocal?

Commercial chat services lock you out once you reach their rigid limits. NexusLocal bypasses this restriction by using your own free API keys across various state-of-the-art providers. When one provider hits a rate limit, simply switch to another, or let NexusLocal orchestrate them in parallel.

### ✦ Key Features

*   **🧬 Response Fusion (🧬 Fusão)**: Query multiple LLMs in parallel (e.g. Gemini + Llama 3.3 + Groq) and let a referee model consolidate the responses into a single, high-quality answer in real-time.
*   **✦ Prompt Enhancer (Varinha Mágica)**: Optimizes your simple queries using a secondary prompt-engineering LLM before sending it to the main model.
*   **💻 Split-Screen Artifacts**: Renders code, HTML, SVG, and documents in an interactive split-screen panel (similar to Claude Artifacts).
*   **🧠 Local Memory**: Persists your conversations, context, and project settings locally via an SQLite database.
*   **⚡ Ultra-Fast Execution**: Built with WebSockets for instant streaming response delivery.

---

## 🛠️ Tech Stack

*   **Frontend**: React 18 + TypeScript + Vite + Zustand (State Management)
*   **Backend**: Python + FastAPI + WebSockets + aiosqlite
*   **Database**: SQLite (Local persistence for chats and configs)

---

## ⚡ Supported Providers & Free Tiers

| Provider | Free Tier Highlights | Key Source |
| :--- | :--- | :--- |
| **Google Gemini** | 1500 req/day (Generous limits) | [Google AI Studio](https://aistudio.google.com/apikey) |
| **Groq** | ~14k req/day (Ultra-fast inference) | [Groq Console](https://console.groq.com) |
| **OpenRouter** | 50+ free models | [OpenRouter Keys](https://openrouter.ai/keys) |
| **SambaNova** | High-speed Llama 3.3 405B access | [SambaNova Cloud](https://cloud.sambanova.ai) |
| **Cerebras** | Insanely fast Llama inference | [Cerebras Cloud](https://cloud.cerebras.ai) |
| **NVIDIA NIM** | $25 initial developer credits | [NVIDIA Build](https://build.nvidia.com) |
| **SiliconFlow** | Multi-LLM provider registry | [SiliconFlow](https://siliconflow.cn) |
| **FreeTheAI** | 50+ models, check-in based | [FreeTheAI](https://freetheai.xyz) |

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/Henzen3d/nexus-local.git
cd nexus-local
```

### 2. Startup local servers

#### Linux / macOS
```bash
chmod +x start.sh
./start.sh
```

#### Windows
Simply run:
```cmd
start.bat
```

### 3. Add your API Keys
Access **`http://localhost:5173`** in your browser, go to **Settings (Configurações)**, and input your API keys to begin chatting limit-free.

---

## 📂 Project Structure

```
nexus-local/
├── backend/
│   ├── main.py              ← FastAPI main application entry point
│   ├── database.py          ← SQLite database initialization and schemas
│   ├── models.py            ← Pydantic data schemas
│   ├── providers/
│   │   ├── base.py          ← OpenAI-compatible base adapter
│   │   └── registry.py      ← API routing logic per provider
│   └── routers/             ← HTTP / WebSocket routes (chat, admin, artifacts)
└── frontend/
    └── src/
        ├── components/      ← Sidebar, ChatWindow, AdminPanel, ArtifactPanel
        ├── store/           ← Zustand global stores (useStore)
        └── index.css        ← Semantic Design System and theme definitions
```

---

## 🗺️ Roadmap

*   [ ] **Self-Scaffold**: Autonomous evaluation loop inspired by Ornith.
*   [ ] **System Prompts**: Customizable system instructions and personas per chat.
*   [ ] **Export Mode**: Export conversations as Markdown or JSON.
*   [ ] **Inline Editing**: Real-time editing and previewing inside the Artifact panel.
