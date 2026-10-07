"""One small real API request; no arena state, retries, or credential output."""
import argparse
from dataclasses import replace
import json

from competition.arena.cli import _client
from r3e.providers.openai_compatible import OpenAICompatibleJSONClient


def probe(client):
    if not client.readiness()["ready"]:
        raise ValueError("请先设置 API Key 和 Base URL 环境变量")
    result = client.complete_json(messages=[
        {"role": "system", "content": 'Return only this JSON object: {"ok": true}'},
        {"role": "user", "content": 'Return JSON {"ok": true}.'},
    ], seed=1)
    if result["result"] != {"ok": True}:
        raise ValueError("接口已返回，但 JSON 内容未通过探测检查")
    return {"ok": True, "network_calls": 1, "model": client.config.model_id,
            "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
            "message": "接口连通和 JSON 输出检查通过；尚未进行 RTL 修复或五轮实验。"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-config", required=True)
    args = parser.parse_args()
    try:
        # Reduce only this probe's output limit, never edit the experiment config.
        config = replace(_client(args.client_config).config, maximum_output_tokens=128)
        result = probe(OpenAICompatibleJSONClient(config))
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
