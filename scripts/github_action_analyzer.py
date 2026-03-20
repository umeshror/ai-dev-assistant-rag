"""
scripts/github_action_analyzer.py
──────────────────────────────────────────────────────────────────────────────
Helper script for GitHub Actions: identifies changed files, analyzes them using
the AI Developer Assistant API, and formats the results for a PR comment.

Environment Variables:
  RAG_API_URL: Base URL of the AI Developer Assistant API (e.g., http://api.service.com)
  GITHUB_TOKEN: GitHub token for API access (provided by GITHUB_ACTIONS)
  GITHUB_EVENT_PATH: Path to the JSON payload of the event that triggered the workflow
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Allowed file extensions for analysis
ALLOWED_EXTENSIONS = {".tf", ".yaml", ".yml", ".py"}


def get_changed_files() -> List[str]:
    """
    Get the list of files changed in the current PR.
    Uses 'git diff' to compare the current branch with the base branch.
    """
    try:
        # For pull_request events, the base branch is typically GITHUB_BASE_REF
        base_ref = os.getenv("GITHUB_BASE_REF", "main")
        logger.info("Identifying changed files relative to '%s'...", base_ref)

        cmd = ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        files = result.stdout.splitlines()

        logger.info("Found %d changed file(s).", len(files))
        return files
    except subprocess.CalledProcessError as err:
        logger.error("Failed to get changed files: %s", err)
        return []


def filter_relevant_files(files: List[str]) -> List[str]:
    """Filter files based on allowed extensions."""
    relevant = [f for f in files if any(f.endswith(ext) for ext in ALLOWED_EXTENSIONS)]
    logger.info("Found %d relevant file(s) for analysis.", len(relevant))
    return relevant


def analyze_file(api_url: str, file_path: str) -> Optional[Dict[str, Any]]:
    """
    Analyze a single file using the RAG API.
    """
    if not os.path.exists(file_path):
        logger.warning("File not found: %s", file_path)
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as err:
        logger.error("Failed to read file %s: %s", file_path, err)
        return None

    if not code.strip():
        logger.info("Skipping empty file: %s", file_path)
        return None

    # Determine type based on extension
    ext = os.path.splitext(file_path)[1]
    if ext == ".tf":
        file_type = "terraform"
    elif ext in {".yaml", ".yml"}:
        file_type = "yaml"
    else:
        file_type = "code"

    logger.info("Analyzing %s [%s]...", file_path, file_type)

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{api_url}/analyze",
                json={"code": code, "type": file_type},
            )
            resp.raise_for_status()
            return resp.json()["analysis"]
    except httpx.HTTPError as err:
        logger.error("API call failed for %s: %s", file_path, err)
        return None
    except Exception as err:
        logger.error("Unexpected error during analysis of %s: %s", file_path, err)
        return None


def format_markdown_comment(results: Dict[str, Dict[str, Any]]) -> str:
    """
    Format the analysis results into a structured Markdown comment.
    """
    if not results:
        return "## 🤖 AI Code Review\n\n✅ No issues found in the analyzed files."

    comment = "## 🤖 AI Code Review\n\n"
    comment += "Code analysis complete. Below is a summary of identified issues.\n\n"

    total_violations = 0
    total_risks = 0

    for file_path, analysis in results.items():
        violations = analysis.get("violations", [])
        risks = analysis.get("security_risks", [])
        suggestions = analysis.get("suggestions", [])

        total_violations += len(violations)
        total_risks += len(risks)

        status_icon = "❌" if violations else "⚠️" if risks else "✅"
        comment += f"### {status_icon} `{file_path}`\n\n"

        if violations:
            comment += "#### ❌ Violations\n"
            for v in violations:
                comment += f"- {v}\n"
            comment += "\n"

        if risks:
            comment += "#### ⚠️ Risks\n"
            for r in risks:
                comment += f"- {r}\n"
            comment += "\n"

        if suggestions:
            comment += "#### 💡 Suggestions\n"
            for s in suggestions:
                comment += f"- {s}\n"
            comment += "\n"

    # Add summary
    comment += "---\n"
    comment += f"**Summary**: Found {total_violations} violation(s) and {total_risks} security risk(s).\n"

    if total_violations > 0:
        comment += "\n🚨 **Action Required**: Please address the policy violations before merging."

    return comment


def main() -> None:
    api_url = os.getenv("RAG_API_URL")
    if not api_url:
        logger.error("RAG_API_URL environment variable not set.")
        sys.exit(1)

    changed_files = get_changed_files()
    relevant_files = filter_relevant_files(changed_files)

    if not relevant_files:
        logger.info("No relevant files to analyze. Exiting.")
        return

    all_results = {}
    total_violations = 0

    for file_path in relevant_files:
        result = analyze_file(api_url, file_path)
        if result:
            all_results[file_path] = result
            total_violations += len(result.get("violations", []))

    # Generate the comment
    comment_body = format_markdown_comment(all_results)

    # Output for GitHub Actions
    # We can use GITHUB_OUTPUT to pass the comment body to a subsequent step
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        # Escape newlines for multi-line output value
        encoded_comment = comment_body.replace("\n", "%0A").replace("\r", "%0D")
        with open(output_path, "a") as f:
            f.write(f"comment_body={comment_body}\n")
            f.write(f"violations_found={total_violations}\n")

    # Also print to stdout for logging
    print("\n" + comment_body)

    # Fail the script if violations are found
    if total_violations > 0:
        logger.error("Found %d violations. Failing workflow.", total_violations)
        sys.exit(1)


if __name__ == "__main__":
    main()
