#!/usr/bin/env python3
"""
SWE-bench runner with DeepSeek v3 integration.

This script:
1. Loads SWE-bench tasks from HuggingFace
2. Uses DeepSeek v3 to generate patches
3. Runs the official SWE-bench harness to evaluate

Usage:
    DEEPSEEK_API_KEY=... python scripts/run_swebench.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from datasets import load_dataset

from controller.llm_client import LLMClient, LLMConfig


@dataclass
class PatchResult:
    instance_id: str
    model_patch: str
    prompt_tokens: int
    completion_tokens: int
    error: str | None = None


SYSTEM_PROMPT = """You are an expert software engineer tasked with fixing bugs in Python repositories.

Given a problem statement describing a bug, you must:
1. Understand the issue
2. Generate a minimal git patch to fix it

Output ONLY the git diff patch content. Use this exact format:
```
diff --git a/path/to/file.py b/path/to/file.py
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -line,count +line,count @@
 context line (unchanged)
-line to remove
+line to add
 context line (unchanged)
```

Rules:
- Generate ONLY the diff, no explanations
- Use proper git diff format with --- and +++ headers
- Include sufficient context lines (3 before and after changes)
- Make minimal changes to fix the issue
- Do not modify unrelated code"""


def generate_patch(client: LLMClient, task: dict) -> PatchResult:
    """Generate a patch for a SWE-bench task using DeepSeek."""
    instance_id = task["instance_id"]
    
    user_prompt = f"""Repository: {task["repo"]}
Base commit: {task["base_commit"]}

Problem Statement:
{task["problem_statement"]}

{'-' * 60}
Generate the minimal git patch to fix this issue."""

    try:
        response = client.complete(
            system=SYSTEM_PROMPT,
            user=user_prompt,
            temperature=0.2,
            max_tokens=4096,
        )
        
        # Extract patch from response
        patch = response.content.strip()
        
        # Clean up code fences if present
        if patch.startswith("```"):
            lines = patch.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            patch = "\n".join(lines)
        
        return PatchResult(
            instance_id=instance_id,
            model_patch=patch,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
        )
    except Exception as e:
        return PatchResult(
            instance_id=instance_id,
            model_patch="",
            prompt_tokens=0,
            completion_tokens=0,
            error=str(e),
        )


def run_swebench_evaluation(
    predictions_path: str,
    instance_ids: list[str] | None = None,
    run_id: str = "deepseek_run",
) -> dict:
    """Run the official SWE-bench evaluation harness."""
    cmd = [
        "python", "-m", "swebench.harness.run_evaluation",
        "--predictions_path", predictions_path,
        "--run_id", run_id,
        "--max_workers", "1",
    ]
    
    if instance_ids:
        cmd.extend(["--instance_ids"] + instance_ids)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Evaluation timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Run SWE-bench with DeepSeek v3")
    parser.add_argument("--limit", type=int, default=5, help="Max tasks to run")
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Lite", help="Dataset name")
    parser.add_argument("--out", default="./swebench_results", help="Output directory")
    parser.add_argument("--skip-eval", action="store_true", help="Only generate patches, skip evaluation")
    args = parser.parse_args()
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("ERROR: DEEPSEEK_API_KEY not set")
        return 1
    
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize DeepSeek client
    config = LLMConfig(
        provider="deepseek",
        model="deepseek-chat",
        temperature=0.2,
        max_tokens=4096,
        timeout=60.0,
    )
    client = LLMClient(config)
    
    # Load dataset
    print(f"Loading dataset: {args.dataset}")
    dataset = load_dataset(args.dataset, split="test")
    tasks = list(dataset)[:args.limit]
    print(f"Loaded {len(tasks)} tasks")
    
    # Generate patches
    print("\n" + "=" * 60)
    print("GENERATING PATCHES")
    print("=" * 60)
    
    predictions = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    for i, task in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] {task['instance_id']}")
        print(f"  Repo: {task['repo']}")
        
        result = generate_patch(client, task)
        
        if result.error:
            print(f"  ERROR: {result.error}")
        else:
            print(f"  Tokens: {result.prompt_tokens} prompt, {result.completion_tokens} completion")
            print(f"  Patch length: {len(result.model_patch)} chars")
            total_prompt_tokens += result.prompt_tokens
            total_completion_tokens += result.completion_tokens
        
        # Format for SWE-bench
        predictions.append({
            "instance_id": result.instance_id,
            "model_name_or_path": "deepseek-chat",
            "model_patch": result.model_patch,
        })
    
    # Save predictions
    predictions_path = out_dir / "predictions.jsonl"
    with open(predictions_path, "w") as f:
        for pred in predictions:
            f.write(json.dumps(pred) + "\n")
    
    print(f"\n{'=' * 60}")
    print(f"GENERATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Tasks processed: {len(predictions)}")
    print(f"Total prompt tokens: {total_prompt_tokens}")
    print(f"Total completion tokens: {total_completion_tokens}")
    print(f"Predictions saved: {predictions_path}")
    
    # Run evaluation (optional)
    if not args.skip_eval:
        print(f"\n{'=' * 60}")
        print("RUNNING EVALUATION")
        print("=" * 60)
        
        instance_ids = [p["instance_id"] for p in predictions]
        eval_result = run_swebench_evaluation(
            str(predictions_path),
            instance_ids=instance_ids,
        )
        
        if eval_result.get("success"):
            print("Evaluation completed successfully!")
            print(eval_result.get("stdout", ""))
        else:
            print(f"Evaluation failed: {eval_result.get('error', eval_result.get('stderr', 'Unknown error'))}")
    
    return 0


if __name__ == "__main__":
    exit(main())
