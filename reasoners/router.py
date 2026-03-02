from agentfield import AgentRouter

router = AgentRouter(tags=["reactive-intelligence"])

from . import skills  # noqa: E402, F401
from . import intelligence  # noqa: E402, F401
