"""
demo.py
──────────────────────────────────────────────────────────────────────────────
Interactive demo for the AI Developer Assistant (RAG-based).

Runs a series of structured test cases against the live /analyze endpoint
and prints rich, colourised output so you can see exactly what the system
catches across Terraform, YAML, and application code inputs.

Usage (server must be running on localhost:8000):
    python demo.py                    # run all scenarios
    python demo.py --url http://...   # custom server URL
    python demo.py --scenario 2       # run only scenario #2

Prerequisites:
    1. `cp .env.example .env` and set OPENAI_API_KEY
    2. `python scripts/ingest.py`
    3. `uvicorn app.main:app --port 8000` (in a separate terminal)
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Dict, List, Optional, Any

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ── ANSI colour helpers ────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
PURPLE = "\033[95m"
GREY   = "\033[90m"
WHITE  = "\033[97m"
BG_DARK = "\033[40m"

def _c(text: str, *codes: str) -> str:
    return "".join(codes) + str(text) + RESET

def _header(title: str) -> None:
    width = 70
    print()
    print(_c("═" * width, CYAN, BOLD))
    print(_c(f"  {title}", CYAN, BOLD))
    print(_c("═" * width, CYAN, BOLD))

def _section(label: str) -> None:
    print(_c(f"\n  ── {label} ──", GREY))

def _item(text: str, color: str = WHITE) -> None:
    print(_c(f"    • {text}", color))

def _success(msg: str) -> None:
    print(_c(f"  ✅  {msg}", GREEN))

def _warning(msg: str) -> None:
    print(_c(f"  ⚠️   {msg}", YELLOW))

def _error(msg: str) -> None:
    print(_c(f"  ❌  {msg}", RED))

def _info(msg: str) -> None:
    print(_c(f"  ℹ️   {msg}", CYAN))

# ── Demo Scenarios ─────────────────────────────────────────────────────────────

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id":          1,
        "title":       "Terraform — Public S3 Bucket + No Encryption",
        "description": "Detects public ACL, missing encryption, and no versioning on an S3 bucket.",
        "type":        "terraform",
        "code":        """\
resource "aws_s3_bucket" "company_data" {
  bucket = "company-customer-data"
  acl    = "public-read"

  tags = {
    Name = "Customer Data"
  }
}

resource "aws_s3_bucket_website_configuration" "site" {
  bucket = aws_s3_bucket.company_data.id

  index_document {
    suffix = "index.html"
  }
}
""",
    },
    {
        "id":          2,
        "title":       "Terraform — Hardcoded Secrets + Overly Permissive IAM",
        "description": "Finds hardcoded DB password, wildcard IAM actions, and AdministratorAccess.",
        "type":        "terraform",
        "code":        """\
resource "aws_db_instance" "prod_db" {
  identifier        = "prod-postgres"
  engine            = "postgres"
  instance_class    = "db.t3.medium"
  username          = "admin"
  password          = "SuperSecret123!"     # HARDCODED!
  publicly_accessible = true
  storage_encrypted = false
}

resource "aws_iam_policy" "app_policy" {
  name = "app-full-access"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "admin" {
  role       = aws_iam_role.app_role.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
""",
    },
    {
        "id":          3,
        "title":       "Terraform — Open Security Group + HTTP Only",
        "description": "Catches SSH/RDP open to 0.0.0.0/0 and HTTP traffic without HTTPS redirect.",
        "type":        "terraform",
        "code":        """\
resource "aws_security_group" "app_sg" {
  name        = "application-sg"
  description = "Allow all inbound traffic"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]    # SSH open to world!
  }

  ingress {
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]    # RDP open to world!
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"         # No HTTPS redirect!
}
""",
    },
    {
        "id":          4,
        "title":       "YAML — Kubernetes Pod: Privileged + No Resource Limits",
        "description": "Detects privileged container, ubuntu:latest image, and missing resource limits/requests.",
        "type":        "yaml",
        "code":        """\
apiVersion: v1
kind: Pod
metadata:
  name: payment-processor
  namespace: production
spec:
  containers:
  - name: payment-app
    image: ubuntu:latest           # Non-minimal base image!
    command: ["python", "app.py"]
    env:
    - name: DB_PASSWORD
      value: "prod-db-secret-123"  # Hardcoded secret!
    - name: API_KEY
      value: "sk-live-abcd1234"    # Hardcoded API key!
    securityContext:
      privileged: true             # Running as privileged!
      runAsUser: 0                 # Running as root!
    ports:
    - containerPort: 8080
    # No resources block — missing CPU/memory limits!
""",
    },
    {
        "id":          5,
        "title":       "YAML — GitHub Actions CI/CD: Insecure Workflow",
        "description": "Finds secrets echoed to logs, no authentication on deploy, and HTTP endpoints.",
        "type":        "yaml",
        "code":        """\
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Print secrets (debug)
        run: |
          echo "API Key: ${{ secrets.API_KEY }}"
          echo "DB Password: ${{ secrets.DB_PASSWORD }}"

      - name: Deploy to server
        run: |
          curl http://internal-deploy-server/deploy \
            --data "image=$IMAGE_TAG"

      - name: Run DB migrations
        env:
          DATABASE_URL: "postgresql://admin:password123@prod-db:5432/app"
        run: python manage.py migrate
""",
    },
    {
        "id":          6,
        "title":       "Application Code — Python: Multiple Security Vulnerabilities",
        "description": "Identifies hardcoded credentials, SQL injection, unauthenticated endpoints, HTTP usage.",
        "type":        "code",
        "code":        """\
import requests
import sqlite3

# Configuration — hardcoded credentials!
DB_PASSWORD = "admin123"
API_SECRET  = "my-super-secret-api-key-abc123"
AWS_KEY     = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET  = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

def get_user(username: str):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    # SQL INJECTION vulnerability!
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cur.execute(query)
    return cur.fetchone()

def call_external_api(data):
    # HTTP instead of HTTPS!
    response = requests.post(
        "http://api.internal-service.com/v1/process",
        json=data,
        headers={"Authorization": f"Bearer {API_SECRET}"}
    )
    return response.json()

def admin_endpoint():
    # No authentication check!
    return {"users": get_all_users(), "secrets": API_SECRET}

def get_all_users():
    conn = sqlite3.connect("app.db")
    # Returns all users with no pagination/auth
    return conn.execute("SELECT * FROM users").fetchall()
""",
    },
    {
        "id":          7,
        "title":       "Terraform — Well-Written (Expect Minimal Issues)",
        "description": "A mostly compliant S3 config — should get few or no violations.",
        "type":        "terraform",
        "code":        """\
resource "aws_s3_bucket" "audit_logs" {
  bucket = "company-audit-logs-${var.environment}"

  tags = {
    Environment = var.environment
    Owner       = "security-team"
    CostCenter  = "CC-1234"
    Project     = "AuditLogging"
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_public_access_block" "audit_logs" {
  bucket                  = aws_s3_bucket.audit_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
  }
}

resource "aws_s3_bucket_versioning" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_logging" "audit_logs" {
  bucket        = aws_s3_bucket.audit_logs.id
  target_bucket = var.access_log_bucket_id
  target_prefix = "audit-logs/"
}
""",
    },
]


# ── API Client ─────────────────────────────────────────────────────────────────


def analyze(base_url: str, code: str, type_: str, timeout: int = 60) -> Dict[str, Any]:
    """Call POST /analyze and return the parsed response dict."""
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{base_url}/analyze",
            json={"code": code, "type": type_},
        )
        resp.raise_for_status()
        return resp.json()


def check_health(base_url: str) -> bool:
    """Return True if the API server is healthy."""
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{base_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


# ── Rendering ─────────────────────────────────────────────────────────────────


def render_result(scenario: Dict[str, Any], result: Dict[str, Any], elapsed: float) -> None:
    analysis = result.get("analysis", {})
    violations    = analysis.get("violations", [])
    risks         = analysis.get("security_risks", [])
    suggestions   = analysis.get("suggestions", [])

    total_issues = len(violations) + len(risks)

    # Summary line
    if total_issues == 0:
        _success(f"No violations found! ({elapsed:.1f}s)")
    elif total_issues <= 2:
        _warning(f"{total_issues} issue(s) found ({elapsed:.1f}s)")
    else:
        _error(f"{total_issues} issue(s) found ({elapsed:.1f}s)")

    # Violations
    if violations:
        _section(f"Policy Violations ({len(violations)})")
        for v in violations:
            _item(v, RED)

    # Security Risks
    if risks:
        _section(f"Security Risks ({len(risks)})")
        for r in risks:
            _item(r, YELLOW)

    # Suggestions
    if suggestions:
        _section(f"Suggestions ({len(suggestions)})")
        for s in suggestions:
            _item(s, GREEN)

    if not violations and not risks and not suggestions:
        _success("Clean code — no policy violations, risks, or suggestions.")


def render_scenario_header(scenario: Dict[str, Any]) -> None:
    sid  = scenario["id"]
    title = scenario["title"]
    desc  = scenario["description"]
    stype = scenario["type"].upper()

    print()
    print(_c(f"\n{'─' * 70}", GREY))
    print(_c(f"  Scenario #{sid} [{stype}]", BOLD, CYAN))
    print(_c(f"  {title}", BOLD, WHITE))
    print(_c(f"  {desc}", GREY))


def render_summary(results: List[Dict[str, Any]]) -> None:
    _header("DEMO SUMMARY")
    total    = len(results)
    success  = sum(1 for r in results if r["status"] == "ok")
    failed   = total - success

    print(f"\n  {'Scenarios run:':<20} {_c(total, BOLD)}")
    print(f"  {'Successful:':<20} {_c(success, GREEN, BOLD)}")
    if failed:
        print(f"  {'Failed:':<20} {_c(failed, RED, BOLD)}")

    total_violations = sum(r.get("violations", 0) for r in results if r["status"] == "ok")
    total_risks      = sum(r.get("risks", 0) for r in results if r["status"] == "ok")

    print(f"\n  {'Total violations:':<20} {_c(total_violations, RED if total_violations else GREEN, BOLD)}")
    print(f"  {'Total risks:':<20} {_c(total_risks, YELLOW if total_risks else GREEN, BOLD)}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demo runner for AI Developer Assistant (RAG-based)"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the API server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--scenario",
        type=int,
        default=None,
        help="Run only a specific scenario by ID (default: run all)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Request timeout in seconds (default: 60)",
    )
    args = parser.parse_args()

    _header("AI DEVELOPER ASSISTANT — DEMO RUNNER")
    _info(f"Server: {args.url}")

    # Health check
    print()
    if not check_health(args.url):
        _error(
            f"Cannot reach the API server at {args.url}\n\n"
            "  Please start it first:\n"
            "    uvicorn app.main:app --reload --port 8000\n"
            "  And make sure you've run the ingest step:\n"
            "    python scripts/ingest.py"
        )
        sys.exit(1)
    _success(f"API server is healthy at {args.url}")

    # Select scenarios
    scenarios = SCENARIOS
    if args.scenario is not None:
        scenarios = [s for s in SCENARIOS if s["id"] == args.scenario]
        if not scenarios:
            _error(f"Scenario #{args.scenario} not found. Valid IDs: {[s['id'] for s in SCENARIOS]}")
            sys.exit(1)

    _info(f"Running {len(scenarios)} scenario(s)...")

    summary_rows: List[Dict[str, Any]] = []

    for scenario in scenarios:
        render_scenario_header(scenario)

        start = time.perf_counter()
        try:
            result = analyze(args.url, scenario["code"], scenario["type"], timeout=args.timeout)
            elapsed = time.perf_counter() - start

            analysis = result.get("analysis", {})
            violations  = analysis.get("violations", [])
            risks       = analysis.get("security_risks", [])
            suggestions = analysis.get("suggestions", [])

            render_result(scenario, result, elapsed)
            summary_rows.append({
                "status":     "ok",
                "violations": len(violations),
                "risks":      len(risks),
                "elapsed":    elapsed,
            })

            # Also print raw JSON for inspection
            _section("Raw JSON Response")
            print(_c(json.dumps(result, indent=4), GREY))

        except httpx.HTTPStatusError as exc:
            elapsed = time.perf_counter() - start
            _error(f"HTTP {exc.response.status_code}: {exc.response.text[:200]}")
            summary_rows.append({"status": "failed", "violations": 0, "risks": 0, "elapsed": elapsed})
        except Exception as exc:
            elapsed = time.perf_counter() - start
            _error(f"Request failed: {exc}")
            summary_rows.append({"status": "failed", "violations": 0, "risks": 0, "elapsed": elapsed})

        # Small delay between requests to avoid rate limits
        if len(scenarios) > 1:
            time.sleep(1)

    render_summary(summary_rows)


if __name__ == "__main__":
    main()
