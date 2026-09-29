"""Optional slow preparation using a local OpenAI-compatible LLM endpoint."""
import httpx


class HttpPlanner:
    def __init__(self, url: str, model: str):
        self.url, self.model = url, model

    async def prepare(self, track: dict) -> str:
        descriptions = [event["cue"] for event in track["events"]]
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(self.url, json={"model": self.model,
                "messages": [{"role": "user", "content": (
                    "Write a short energy allocation plan for this robot race. "
                    "Jump and slide are free. Shield and shoot cost one charge. "
                    "Start with 3 charges; restore one every 3 obstacles. "
                    "Do not execute actions. Give at most 150 words. Obstacles: "
                    + str(descriptions))}], "max_tokens": 250, "stream": False})
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"][:2000]
