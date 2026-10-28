"""AI fact extraction + rule-based verification for one batch of proposals.

    pip install -r requirements.txt
    cp .env.example .env            # add your key
    # put proposal text in samples/A.txt ... samples/E.txt (git-ignored)
    python extract.py criteria_solar_v1.json samples extractions.json
    python score.py criteria_solar_v1.json extractions.json

The prompt is read from ../PROMPTS.md so the repo has a single copy of it.
"""
import json
import os
import pathlib
import re
import sys

import anthropic

MODEL = "claude-opus-5-5"
HERE = pathlib.Path(__file__).parent

# Rule-based scan that runs alongside the model's own embedded_instructions report.
INJECTION_PATTERNS = [
    r"automated (review|system)", r"\b(AI|LLM|language model)\b", r"ignore (all|previous|the above)",
    r"rank (it|this|us) (first|#?1)", r"full marks", r"pre-?approved", r"system prompt",
]


def load_env():
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_prompts():
    md = (HERE.parent / "PROMPTS.md").read_text(encoding="utf-8")
    block = lambda heading: re.search(rf"## {heading}\s+```text\n(.*?)```", md, re.S).group(1).strip()
    return block("System prompt"), block("User message template")


def build_schema(config):
    json_type = {"number": "number", "boolean": "boolean", "string": "string"}
    field = lambda t: {
        "type": "object",
        "properties": {
            "value": {"type": [json_type[t], "null"]},
            "evidence": {"type": ["string", "null"]},
            "page": {"type": ["integer", "null"]},
            "note": {"type": ["string", "null"]},
        },
        "required": ["value", "evidence", "page", "note"],
        "additionalProperties": False,
    }
    ids = [f["id"] for f in config["fields"]]
    return {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "properties": {f["id"]: field(f["type"]) for f in config["fields"]},
                "required": ids,
                "additionalProperties": False,
            },
            "embedded_instructions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["fields", "embedded_instructions"],
        "additionalProperties": False,
    }


def normalize(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def verify(result, text):
    """Drop any answer whose evidence quote is not really in the document."""
    doc = normalize(text)
    problems = []
    for fid, ans in result["fields"].items():
        if ans["value"] is not None and (not ans["evidence"] or normalize(ans["evidence"]) not in doc):
            problems.append(f"{fid}: evidence not found in document, value discarded")
            ans["value"] = None
    for pat in INJECTION_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            snippet = text[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
            if not any(normalize(m.group(0)) in normalize(e) for e in result["embedded_instructions"]):
                result["embedded_instructions"].append(f"[pattern scan] ...{snippet}...")
    result["verification_problems"] = problems
    return result


def extract(client, system, template, config, filename, text):
    questions = "\n".join(f"- {f['id']} ({f['type']}): {f['question']}" for f in config["fields"])
    user = (template.replace("{{CATEGORY}}", config["category"])
            .replace("{{CRITERIA_VERSION}}", str(config["criteria_version"]))
            .replace("{{EVALUATION_DATE}}", config["evaluation_date"])
            .replace("{{QUESTIONS}}", questions)
            .replace("{{FILENAME}}", filename)
            .replace("{{PROPOSAL_TEXT}}", text))
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": build_schema(config)}},
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"{filename}: model declined; route to manual review")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"{filename}: output truncated; route to manual review")
    body = next(b.text for b in response.content if b.type == "text")
    result = json.loads(body)
    result["_audit"] = {"model": response.model, "request_id": response.id,
                        "criteria_version": config["criteria_version"]}
    return verify(result, text)


def main(config_path, samples_dir, out_path):
    load_env()
    config = json.load(open(config_path, encoding="utf-8"))
    system, template = load_prompts()
    client = anthropic.Anthropic()
    out = {}
    for path in sorted(pathlib.Path(samples_dir).glob("*.txt")):
        print(f"extracting {path.name}", file=sys.stderr)
        out[path.stem] = extract(client, system, template, config, path.name,
                                 path.read_text(encoding="utf-8"))
    json.dump(out, open(out_path, "w", encoding="utf-8"), indent=2)


if __name__ == "__main__":
    main(*sys.argv[1:4])
