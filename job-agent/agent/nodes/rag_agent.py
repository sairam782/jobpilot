"""RAG helper node for answering custom application questions."""

import httpx

from agent.schemas import AgentState


class RAGToolAgent:
    """Calls the local /resume_qa endpoint for custom question answers."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    async def answer(self, question: str) -> str:
        """Return a resume-grounded answer for a custom application question."""

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.base_url}/resume_qa", json={"question": question})
            response.raise_for_status()
            return str(response.json()["answer"])

    async def __call__(self, state: AgentState) -> AgentState:
        """Placeholder graph node for future question-detection routing."""

        return state
