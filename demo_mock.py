"""
demo_mock.py
──────────────────────────────────────────────────────────────────────────────
Fully self-contained demo — NO OpenAI API key or running server required.
Modular Refactor Edition.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

# ── Ensure project root is on path ────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set a fake API key for pydantic-settings validation
os.environ.setdefault("OPENAI_API_KEY", "sk-mock-key-for-demo")

# ── App Modular Imports ───────────────────────────────────────────────────────
from app.core.config import get_settings
from app.models.analysis import AnalysisResult, AnalyzeRequest, AnalyzeResponse
from app.services.analyzer import AnalyzerService
from app.engines.rag import RAGEngine
from app.engines.llm import LLMClient

# ── ANSI colour helpers (omitted for brevity in this scratch, but kept in final) ──
RESET, BOLD, RED, GREEN, YELLOW, CYAN, PURPLE, GREY, WHITE, DIM = (
    "\033[0m", "\033[1m", "\033[91m", "\033[92m", "\033[93m", "\033[96m", "\033[95m", "\033[90m", "\033[97m", "\033[2m"
)
def _c(t, *c): return "".join(c) + str(t) + RESET
def _header(t): print(f"\n{_c('═'*72, CYAN, BOLD)}\n{_c('  '+t, CYAN, BOLD)}\n{_c('═'*72, CYAN, BOLD)}")
def _scenario_header(sid, stype, title, desc):
    print(f"\n{_c('─'*72, GREY)}\n{_c(f'  Scenario #{sid}  [{stype.upper()}]', BOLD, CYAN)}\n{_c(f'  {title}', BOLD, WHITE)}\n{_c(f'  {desc}', DIM, GREY)}")

# ── Mock LLM Data ─────────────────────────────────────────────────────────────
MOCK_RESPONSES = {
    1: {"violations": ["Public S3 bucket ACL."], "security_risks": ["Data leak."], "suggestions": ["Enable Block Public Access."]},
    2: {"violations": ["Hardcoded DB password."], "security_risks": ["Credential theft."], "suggestions": ["Use Secrets Manager."]},
    3: {"violations": ["SSH open to 0.0.0.0/0."], "security_risks": ["Brute force attack."], "suggestions": ["Restrict SSH to VPN CIDR."]},
    4: {"violations": ["Privileged container."], "security_risks": ["Host escape."], "suggestions": ["Set privileged: false."]},
    5: {"violations": ["GitHub secrets echoed."], "security_risks": ["Log exposure."], "suggestions": ["Use mask-secret command."]},
    6: {"violations": ["AWS keys in code."], "security_risks": ["Account takeover."], "suggestions": ["Use IAM roles."]},
    7: {"violations": [], "security_risks": [], "suggestions": ["Add S3 MFA Delete."]},
}

SCENARIOS = [
    {"id": 1, "title": "S3 Public", "type": "terraform", "code": "resource 'aws_s3_bucket' 'p' { acl='public-read' }"},
    {"id": 2, "title": "Secrets", "type": "terraform", "code": "password = '123'"},
    {"id": 3, "title": "SSH Open", "type": "terraform", "code": "ingress { port=22 cidr='0.0.0.0/0' }"},
    {"id": 4, "title": "K8s Root", "type": "yaml", "code": "privileged: true"},
    {"id": 5, "title": "CI Secrets", "type": "yaml", "code": "run: echo ${{ secrets.KEY }}"},
    {"id": 6, "title": "Hardcoded Python", "type": "code", "code": "AWS_KEY = 'AKIA...'"},
    {"id": 7, "title": "Compliant S3", "type": "terraform", "code": "resource 'aws_s3_bucket' 'ok' { versioning { enabled=true } }"},
]

async def run_mock_pipeline(scenario: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    
    # Mock Engines
    mock_rag = MagicMock(spec=RAGEngine)
    mock_rag.retrieve = AsyncMock(return_value=["Mock Policy 1", "Mock Policy 2"])
    
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.analyze = AsyncMock(return_value=MOCK_RESPONSES[scenario["id"]])
    
    # Initialize real Service with mock engines
    analyzer = AnalyzerService(settings, mock_rag, mock_llm)
    
    # Run pipeline
    req = AnalyzeRequest(code=scenario["code"], type=scenario["type"])
    response = await analyzer.analyze_code(req, request_id="demo-mock-refactor")
    return response.model_dump()

async def _main():
    _header("AI DEVELOPER ASSISTANT — MODULAR REFACTOR DEMO")
    summary = []
    for s in SCENARIOS:
        _scenario_header(s["id"], s["type"], s["title"], "Refactored modular pipeline test")
        start = time.perf_counter()
        res = await run_mock_pipeline(s)
        elapsed = time.perf_counter() - start
        
        # Simple output for refactor verification
        v, r, sug = len(res["analysis"]["violations"]), len(res["analysis"]["security_risks"]), len(res["analysis"]["suggestions"])
        print(f"    {_c('SUCCESS', GREEN)} | Issues: {v+r} | Remediations: {sug} | Time: {elapsed:.3f}s")
        summary.append(res)
    
    print(f"\n{_c('DONE', GREEN, BOLD)}: All 7 scenarios passed modular refactor check.")

if __name__ == "__main__":
    asyncio.run(_main())
