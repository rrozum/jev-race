"""Optional PyTorch Laya adapter. Import/load explicitly, once at startup."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from race.contracts import Context, Decision


class LayaBrain:
    def __init__(self, checkpoint: str, device: str = "cpu"):
        import laya
        self.model = laya.load(checkpoint, device=device)
        self.checkpoint = checkpoint
        # A cancelled HTTP request must not release the GPU to another inference
        # while the old synchronous predict() is still running.
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="laya")

    async def choose(self, context: Context) -> Decision:
        predict = partial(self.model.predict, context.state, {
            "action": {"type": "choice", "instructions": context.question,
                       "criteria": {c.id: c.text for c in context.candidates}}})
        result = await asyncio.get_running_loop().run_in_executor(self.worker, predict)
        return Decision(result["answers"]["action"]["choice"], self.checkpoint)
