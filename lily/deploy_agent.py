"""Lily deploy agent — professional install, start, stop, and status steps.

This module is intentionally non-destructive by default. Destructive steps
(stop, restart) only touch processes Lily started under the local run directory.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / ".lily_run"
PID_BOT = RUN_DIR / "bot.pid"
PID_API = RUN_DIR / "api.pid"
LOG_BOT = RUN_DIR / "bot.log"
LOG_API = RUN_DIR / "api.log"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class DeployReport:
    steps: list[StepResult] = field(default_factory=list)
    ok: bool = True

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(StepResult(name, ok, detail))
        if not ok:
            self.ok = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "steps": [{"name": s.name, "ok": s.ok, "detail": s.detail} for s in self.steps],
        }


def _python() -> str:
    return os.environ.get("LILY_PYTHON_BIN") or sys.executable


def _read_pid(path: Path) -> int | None:
    try:
        value = int(path.read_text().strip())
        return value if value > 0 else None
    except Exception:
        return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _stop_pid(path: Path, label: str) -> str:
    pid = _read_pid(path)
    if not pid:
        path.unlink(missing_ok=True)
        return f"{label}: not running"
    if not _pid_alive(pid):
        path.unlink(missing_ok=True)
        return f"{label}: stale pid {pid} removed"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return f"{label}: could not signal {pid}: {exc}"
    # Wait up to 8s, then SIGKILL
    for _ in range(16):
        if not _pid_alive(pid):
            path.unlink(missing_ok=True)
            return f"{label}: stopped (pid {pid})"
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    path.unlink(missing_ok=True)
    return f"{label}: force-stopped (pid {pid})"


def ensure_run_dir() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "work").mkdir(parents=True, exist_ok=True)
    (ROOT / "downloads").mkdir(parents=True, exist_ok=True)


def check_env() -> tuple[bool, str]:
    if not ENV_FILE.exists():
        return False, ".env missing — copy .env.example and set TELEGRAM_BOT_TOKEN"
    text = ENV_FILE.read_text(encoding="utf-8", errors="replace")
    if "TELEGRAM_BOT_TOKEN=" not in text or "TELEGRAM_BOT_TOKEN=\n" in text or 'TELEGRAM_BOT_TOKEN=""' in text:
        # soft check
        token_line = next((line for line in text.splitlines() if line.startswith("TELEGRAM_BOT_TOKEN=")), "")
        value = token_line.split("=", 1)[-1].strip().strip('"').strip("'")
        if not value or value in {"changeme", "YOUR_TOKEN", "xxx"}:
            return False, "TELEGRAM_BOT_TOKEN is not set in .env"
    return True, "`.env` present"


def install_dependencies(*, upgrade: bool = False) -> StepResult:
    req = ROOT / "requirements.txt"
    if not req.exists():
        return StepResult("install_dependencies", False, "requirements.txt not found")
    cmd = [_python(), "-m", "pip", "install", "-r", str(req)]
    if upgrade:
        cmd.insert(4, "--upgrade")
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-400:]
            return StepResult("install_dependencies", False, tail or f"exit {proc.returncode}")
        return StepResult("install_dependencies", True, "requirements installed")
    except Exception as exc:
        return StepResult("install_dependencies", False, str(exc)[:300])


def write_env_from_example() -> StepResult:
    if ENV_FILE.exists():
        return StepResult("env", True, ".env already exists")
    if not ENV_EXAMPLE.exists():
        return StepResult("env", False, ".env.example missing")
    ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass
    return StepResult("env", True, "created .env from .env.example — edit TELEGRAM_BOT_TOKEN")


def status_snapshot() -> dict[str, Any]:
    bot_pid = _read_pid(PID_BOT)
    api_pid = _read_pid(PID_API)
    return {
        "root": str(ROOT),
        "bot": {"pid": bot_pid, "running": _pid_alive(bot_pid), "log": str(LOG_BOT)},
        "api": {"pid": api_pid, "running": _pid_alive(api_pid), "log": str(LOG_API)},
        "env_ok": check_env()[0],
        "run_dir": str(RUN_DIR),
    }


def start_bot(*, foreground: bool = False) -> StepResult:
    ensure_run_dir()
    ok, detail = check_env()
    if not ok:
        return StepResult("start_bot", False, detail)
    existing = _read_pid(PID_BOT)
    if _pid_alive(existing):
        return StepResult("start_bot", True, f"already running (pid {existing})")
    if foreground:
        # Caller execs — we just validate
        return StepResult("start_bot", True, "ready for foreground launch")
    log_handle = LOG_BOT.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [_python(), "-m", "lily.main"],
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={**os.environ},
    )
    PID_BOT.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(0.4)
    if not _pid_alive(proc.pid):
        return StepResult("start_bot", False, f"process exited early — see {LOG_BOT}")
    return StepResult("start_bot", True, f"started pid {proc.pid} (log: {LOG_BOT})")


def start_api(*, port: int | None = None) -> StepResult:
    ensure_run_dir()
    existing = _read_pid(PID_API)
    if _pid_alive(existing):
        return StepResult("start_api", True, f"already running (pid {existing})")
    port = int(port or os.environ.get("PORT") or 8080)
    log_handle = LOG_API.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [_python(), "-m", "uvicorn", "lily.web_media:create_app", "--factory", "--host", "0.0.0.0", "--port", str(port)],
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={**os.environ, "PORT": str(port)},
    )
    PID_API.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(0.4)
    if not _pid_alive(proc.pid):
        return StepResult("start_api", False, f"API exited early — see {LOG_API}")
    return StepResult("start_api", True, f"started pid {proc.pid} on :{port}")


def stop_all() -> list[StepResult]:
    return [
        StepResult("stop_bot", True, _stop_pid(PID_BOT, "bot")),
        StepResult("stop_api", True, _stop_pid(PID_API, "api")),
    ]


def restart_all(*, with_api: bool = False, port: int | None = None) -> DeployReport:
    report = DeployReport()
    for step in stop_all():
        report.add(step.name, step.ok, step.detail)
    time.sleep(0.5)
    bot = start_bot()
    report.add(bot.name, bot.ok, bot.detail)
    if with_api:
        api = start_api(port=port)
        report.add(api.name, api.ok, api.detail)
    return report


def full_install_agent(*, with_deps: bool = True, start: bool = False, with_api: bool = False) -> DeployReport:
    """Full guided install: dirs → env → deps → optional start."""
    report = DeployReport()
    ensure_run_dir()
    report.add("directories", True, "data/, work/, downloads/, .lily_run/ ready")

    env_step = write_env_from_example()
    report.add(env_step.name, env_step.ok, env_step.detail)

    ok, detail = check_env()
    report.add("env_check", ok, detail)

    if with_deps:
        dep = install_dependencies()
        report.add(dep.name, dep.ok, dep.detail)

    if start and report.ok:
        bot = start_bot()
        report.add(bot.name, bot.ok, bot.detail)
        if with_api:
            api = start_api()
            report.add(api.name, api.ok, api.detail)
    return report


def clone_and_setup_guide(repo_url: str = "https://github.com/Beasgohan-code/lily-ai-telegram-bot.git") -> list[str]:
    """Return copy-paste commands for a clean VPS / server install."""
    return [
        "# 1) System packages (Ubuntu/Debian)",
        "sudo apt update && sudo apt install -y git python3 python3-pip python3-venv ffmpeg",
        "",
        "# 2) Clone",
        f"git clone {repo_url} lily-ai-telegram-bot",
        "cd lily-ai-telegram-bot",
        "",
        "# 3) Virtualenv",
        "python3 -m venv .venv",
        "source .venv/bin/activate",
        "pip install -U pip",
        "pip install -r requirements.txt",
        "",
        "# 4) Configure",
        "cp .env.example .env",
        "nano .env   # set TELEGRAM_BOT_TOKEN and optional OPENAI_API_KEY / LILY_AI_KEYS",
        "",
        "# 5) Professional CLI install + start",
        "python3 -m lily.cli host install",
        "python3 -m lily.cli host start",
        "python3 -m lily.cli host status",
        "",
        "# 6) Day-2 ops",
        "python3 -m lily.cli host logs --tail 50",
        "python3 -m lily.cli host stop",
        "python3 -m lily.cli host restart",
        "",
        "# Optional: API bridge (Mini App / streams) on PORT",
        "PORT=8080 python3 -m lily.cli host start --api",
        "",
        "# Optional: foreground debug (no pid file)",
        "bash commands/run-bot.sh",
    ]


def format_steps_markdown(report: DeployReport) -> str:
    lines = ["Lily deploy agent report", ""]
    for index, step in enumerate(report.steps, start=1):
        mark = "OK" if step.ok else "FAIL"
        lines.append(f"{index}. [{mark}] {step.name}: {step.detail}")
    lines.append("")
    lines.append("Overall: " + ("SUCCESS" if report.ok else "NEEDS ATTENTION"))
    return "\n".join(lines)
