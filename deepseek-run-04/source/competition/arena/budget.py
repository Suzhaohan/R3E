"""Persist a conservative call/token reservation before each provider call."""
import json
from pathlib import Path
from r3e.protocol.hashing import atomic_write_json
from r3e.protocol.ledger import writer_lock
from competition.arena.evidence import read

class BudgetedClient:
    def __init__(self, client, path, *, max_calls, max_tokens):
        if max_calls < 1 or max_tokens < 1:
            raise ValueError("positive explicit provider budgets required")
        self.client, self.config = client, client.config
        self._transport = client._transport
        self.path=Path(path)
        self.max_calls, self.max_tokens=max_calls,max_tokens

    def complete_json(self, **kwargs):
        # UTF-8 byte count is a conservative prompt-token reservation, plus
        # protocol overhead and the full configured completion allowance.
        reserve=len(json.dumps(kwargs.get("messages",[]),ensure_ascii=False).encode()) + 1024 + self.config.maximum_output_tokens
        with writer_lock(self.path.with_suffix(".lock")):
            state=read(self.path) if self.path.exists() else {"calls":0,"reserved_tokens":0,"max_calls":self.max_calls,"max_tokens":self.max_tokens}
            if state["max_calls"] != self.max_calls or state["max_tokens"] != self.max_tokens:
                raise ValueError("resume budget differs from frozen reservation")
            if state["calls"]+1>self.max_calls or state["reserved_tokens"]+reserve>self.max_tokens:
                raise RuntimeError("explicit provider budget exhausted; no new call made")
            state["calls"]+=1; state["reserved_tokens"]+=reserve
            atomic_write_json(self.path,state)
        return self.client.complete_json(**kwargs)
