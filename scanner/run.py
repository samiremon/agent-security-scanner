"""Run attacks against an agent command and report what happened."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from scanner.attacks import load_attack
from scanner.scorer import Outcome, Score, score

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMEOUT_SECONDS = 300


@dataclass
class RunResult:
    attack_id: str
    score: Score
    answer: str
    stderr: str


def read_calls(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def run_attack(attack_id: str, agent_command: str, timeout: float = TIMEOUT_SECONDS) -> RunResult:
    attack = load_attack(attack_id)
    with tempfile.TemporaryDirectory(prefix="agent-scan-") as run_dir:
        attack_file = Path(run_dir) / "attack.json"
        call_log = Path(run_dir) / "calls.jsonl"
        attack_file.write_text(json.dumps(attack), encoding="utf-8")
        env = {
            **os.environ,
            "AGENT_TASK": attack["task"],
            "BAIT_ATTACK_FILE": str(attack_file),
            "BAIT_CALL_LOG": str(call_log),
        }
        try:
            process = subprocess.run(
                shlex.split(agent_command),
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            exit_code, answer, stderr = process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired:
            exit_code, answer, stderr = None, "", f"Timed out after {timeout} seconds."
        calls = read_calls(call_log)
    return RunResult(attack_id, score(attack, calls, exit_code, answer), answer.strip(), stderr.strip())


def print_result(result: RunResult) -> None:
    print(f"Attack: {result.attack_id}")
    print(f"Result: {result.score.outcome.value}")
    if result.score.evidence:
        print(f"Evidence: {json.dumps(result.score.evidence)}")
    if result.answer:
        print(f"Agent answer: {result.answer}")
    if result.score.outcome is Outcome.ERROR and result.stderr:
        print(f"Error: {result.stderr[-500:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack", required=True, help="Attack ID, the file name in attacks/")
    parser.add_argument(
        "--agent",
        default=f"{shlex.quote(sys.executable)} -m agents.test_agent",
        help="Command that starts the agent",
    )
    args = parser.parse_args()

    result = run_attack(args.attack, args.agent)
    print_result(result)
    if result.score.outcome is Outcome.ATTACK_SUCCEEDED:
        return 1
    return 2 if result.score.outcome is Outcome.ERROR else 0


if __name__ == "__main__":
    sys.exit(main())
