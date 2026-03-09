import os

from agentfield import Agent, AIConfig

DOMAIN = os.getenv("DOMAIN", "finance")

app = Agent(
    node_id="reactive-intelligence",
    agentfield_server=os.getenv("AGENTFIELD_SERVER", ""),
    api_key=os.getenv("AGENTFIELD_API_KEY"),
    ai_config=AIConfig(
        model=os.getenv("AI_MODEL", "openrouter/minimax/minimax-m2.5"),
    ),
)

from reasoners.router import router  # noqa: E402

app.include_router(router)

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "8001")))
