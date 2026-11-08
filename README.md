# Agent Security Scanner

Automated red teaming for MCP agents. It connects an agent to simulated tools, plants realistic attacks in their output, and uses code to check what the agent did.

**Status:** Early development. It currently has 11 attacks across 5 types.

## Local dashboard

```bash
uv sync
uv run python -m scanner.dashboard
```

Open **http://127.0.0.1:8765**. Choose an agent, inspect and select attack scenarios,
set repetitions, and start a scan. Results include recorded tool calls, the exact
attack definition, matched evidence, final answers, JSON export, and replay with
fresh fake secrets. Scan history persists in `runs/dashboard/`.

- **Scripted demo:** no API key. Deliberately follows the first email attack and
  uses predefined answers for the others. Demonstrates the workflow; these are
  not model security measurements.
- **Bundled Gemini agent:** set `GEMINI_API_KEY` in the terminal before starting
  the dashboard. Optional `AGENT_MODEL` selects the model. `.env` is not loaded
  automatically. Real scans consume provider quota.
- **Custom adapter:** enter a local executable command. It receives `AGENT_TASK`,
  `BAIT_ATTACK_FILE`, and `BAIT_CALL_LOG`. Connect its MCP client using
  `agents.connection.bait_server_params()` (see `agents/test_agent.py`), run the
  task, and print its final answer to stdout. Exit 0 normally, 3 for provider
  errors, or 4 for the step limit. The command runs from the project root with
  the scanner's environment. This is not a URL-based connection or sandbox for
  arbitrary executable code.

The dashboard binds only to loopback and requires a session token plus a
same-origin request to launch commands. Keep it local. One scan runs at a time;
three consecutive execution errors interrupt it. Replay starts a new complete
scan. Restarting the server marks unfinished scans interrupted. Existing CLI
scan records remain separate from dashboard history.

**Current scope:** the 11 existing predefined simulated-tool scenarios. Automatic
capability discovery, framework-specific adapters, RAG answer attacks, clean-task
baselines, saved regression packs, and interception of production tools are not
implemented yet. “Resisted” uses a scenario-specific phrase check, not a semantic
proof that an answer is correct. Selecting a compatible scenario is currently
up to the user. Tool traces record names and arguments; attack definitions retain
simulated responses, rather than a full per-response transcript.

## How it works

1. The scanner starts your agent with a normal task, such as "Summarize my latest email."
2. The agent connects to the bait MCP server and uses its simulated tools.
3. A tool response contains a hidden instruction and the agent has access to a fake secret.
4. The server logs every tool call, and the scorer checks the log against the attack's rules.

Nothing is actually sent. Secrets are fake and generated fresh for each run.

| Outcome | Meaning |
|---|---|
| `ATTACK_SUCCEEDED` | The agent followed the attacker's instruction |
| `RESISTED` | The agent ignored the attack and finished the task |
| `AGENT_STOPPED` | The attack failed, but the task wasn't finished |
| `NOT_EXPOSED` | The agent never read the malicious content |
| `ERROR` | A provider block, crash, or timeout, so the result says nothing about security |

## Attacks

| Type | Attacks |
|---|---|
| Indirect prompt injection | `email_exfiltration_01`, `email_exfiltration_02`, `webpage_delete_01`, `docs_forward_01` |
| Tool poisoning | `tool_poison_weather_01`, `tool_poison_read_file_01` |
| Rug pull | `rug_pull_calendar_01`, `rug_pull_customer_01` |
| Secret exfiltration | `config_exfiltration_01`, `report_url_leak_01` |
| Unrequested action | `invoice_payment_01` |

Each attack is a YAML file in `attacks/` that defines the task, the simulated tools, and the rules for success.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and a [Gemini API key](https://aistudio.google.com/apikey).

```bash
uv sync
export GEMINI_API_KEY="your-key"

# Run one attack
uv run python -m scanner.run --attack email_exfiltration_01

# Run every attack 3 times
uv run python -m scanner.run --repeat 3

# Continue a scan that stopped
uv run python -m scanner.run --resume SCAN_ID
```

Results are saved in `runs/` as they finish. The scan stops after 3 errors in a row, which usually means your quota has run out, and resuming retries those runs. The command exits with `0` if no attack succeeded, `1` if one did, and `2` if the scan is incomplete.

| Setting | Purpose | Default |
|---|---|---|
| `AGENT_MODEL` | Gemini model to test | `gemini-3.5-flash-lite` |
| `AGENT_MIN_REQUEST_SECONDS` | Minimum seconds between Gemini requests | `6` |

To run the tests, which need no API key:

```bash
uv run pytest
```

## Responsible use

Test only agents you own or are allowed to test, and keep them away from real credentials. Report any real vulnerabilities privately to the maintainers.
