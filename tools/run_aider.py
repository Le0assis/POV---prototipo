"""Ponte entre o orquestrador (.agent_bus) e o Aider.

task.json:
    {
      "instruction": "texto da tarefa",
      "files": ["arquivos/editaveis.py"],      # equivalente a /add
      "read":  ["arquivos/somente/contexto"],  # equivalente a /read
      "model": "openai/claude-sonnet-5-5"      # opcional
    }
"""
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_MODEL = "openai/claude-sonnet-5-5"
DEFAULT_READ = ["auditorias/auditoria-003.md", "contexto-IA.md"]
OUTBOX = Path(".agent_bus/outbox/result.json")
TIMEOUT_S = 1200


def build_command(task: dict) -> list[str]:
    cmd = [
        "aider", "--model", task.get("model", DEFAULT_MODEL),
        "--model-metadata-file", ".aider.model.metadata.json",
        "--edit-format", task.get("edit_format", "diff"),
        "--yes-always", "--no-pretty", "--no-stream",
        "--no-show-model-warnings", "--no-check-update", "--no-detect-urls",
        "--no-suggest-shell-commands", "--map-tokens", "1024",
    ]

    for path in task.get("read", DEFAULT_READ):
        if Path(path).exists():
            cmd += ["--read", path]

    cmd += ["--message", task["instruction"]]
    cmd += task.get("files", [])
    return cmd


def run_task(task_file: str) -> int:
    task = json.loads(Path(task_file).read_text(encoding="utf-8"))
    cmd = build_command(task)

    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL)
        output = {
            "status": "success" if res.returncode == 0 else "error",
            "returncode": res.returncode,
            "files": task.get("files", []),
            "log": res.stdout[-4000:],
            "error": res.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        output = {"status": "error", "returncode": -1, "files": task.get("files", []),
                  "log": "", "error": f"timeout apos {TIMEOUT_S}s"}

    payload = json.dumps(output, indent=2, ensure_ascii=False)
    OUTBOX.write_text(payload, encoding="utf-8")
    if task.get("task_id"):
        (OUTBOX.parent / f"{task['task_id']}.json").write_text(payload, encoding="utf-8")
    return 0 if output["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(run_task(sys.argv[1]))
