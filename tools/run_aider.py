import json, subprocess, sys

def run_task(task_file):
    with open(task_file, 'r') as f:
        task = json.load(f)
    
    prompt = f"{task['instruction']}"
    
    # Adicionada a flag --model para usar o modelo cadastrado no seu proxy
    cmd = [
        "aider",
        "--model", "openai/claude-3-5-sonnet-20241022",
        "--read", "auditoria-001.md",
        "--message", prompt,
        "--yes"
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    
    output = {
        "status": "success" if res.returncode == 0 else "error",
        "log": res.stdout[-2000:],
        "error": res.stderr[-2000:]
    }
    
    with open(".agent_bus/outbox/result.json", "w") as f:
        json.dump(output, f, indent=2)

if __name__ == "__main__":
    run_task(sys.argv[1])