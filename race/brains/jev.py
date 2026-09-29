"""A credential is used for one HTTP request, never a default client header."""
import httpx
from race.contracts import Context, Decision

API_URL = "https://api.typesafe.ai/v1/systemone"


class ProviderError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)  # No upstream response body or credential.


class JevBrain:
    def __init__(self, client: httpx.AsyncClient, token: str, model: str = "jev-1.13.0",
                 input_price: float = 0.042):
        self.client, self.token, self.model, self.input_price = client, token, model, input_price

    async def choose(self, context: Context) -> Decision:
        payload = {"state": context.state, "model": self.model, "questions": {
            "action": {"type": "choice", "instructions": context.question,
                       "criteria": {c.id: c.text for c in context.candidates}}}}
        try:
            response = await self.client.post(API_URL, json=payload,
                headers={"Authorization": f"Bearer {self.token}"})
        except httpx.TimeoutException:
            raise ProviderError("timeout") from None
        except httpx.HTTPError:
            raise ProviderError("unavailable") from None
        finally:
            self.token = ""
        if response.status_code in (401, 403):
            raise ProviderError("invalid_token")
        if response.status_code in (429, 529):
            raise ProviderError("rate_limited")
        if response.status_code != 200:
            raise ProviderError("unavailable")
        try:
            data = response.json()
            answer = data["answers"]["action"]
            tokens = data["usage"]["input_tokens"]
            if answer["type"] != "choice" or type(tokens) is not int or tokens < 0:
                raise ValueError()
            return Decision(answer["choice"], data.get("model", self.model), tokens,
                            tokens * self.input_price / 1_000_000)
        except (KeyError, TypeError, ValueError):
            raise ProviderError("invalid_response") from None
