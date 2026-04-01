"""Proactive scheduler — runs agent tasks on cron schedules.

Reads YAML job files from the schedules/ directory and executes them
when their cron expression matches. Runs as a daemon thread alongside
the main polling loop.

Job file format (schedules/*.yaml):
  name: morning_weather
  schedule: "0 7 * * *"
  recipient: "+1234567890"
  prompt: "Research the current weather in Warsaw, Poland."
  enabled: true
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from croniter import croniter

logger = logging.getLogger(__name__)

SCHEDULES_DIR = Path("schedules")


@dataclass
class ScheduledJob:
    """A single scheduled job parsed from YAML."""
    name: str
    schedule: str
    recipient: str
    prompt: str
    enabled: bool = True
    # Optional: call a /command directly instead of going through the LLM
    command: str | None = None
    command_args: str | None = None
    last_run: datetime | None = field(default=None, repr=False)


def _load_jobs() -> list[ScheduledJob]:
    """Load all job definitions from both built-in and external schedules."""
    jobs = []
    dirs = [
        Path("schedules"),           # built-in (shipped with bot)
        Path("data/schedules"),      # external (volume-mounted)
    ]

    for sdir in dirs:
        if not sdir.is_dir():
            continue
        for path in sorted(sdir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            try:
                data = yaml.safe_load(path.read_text())
                job = ScheduledJob(
                    name=data["name"],
                    schedule=data["schedule"],
                    recipient=data["recipient"],
                    prompt=data.get("prompt", ""),
                    enabled=data.get("enabled", True),
                    command=data.get("command"),
                    command_args=data.get("command_args", ""),
                )
                if job.enabled:
                    jobs.append(job)
                    logger.info("Loaded scheduled job: %s (%s) from %s", job.name, job.schedule, sdir)
                else:
                    logger.info("Skipping disabled job: %s", job.name)
            except Exception as e:
                logger.error("Failed to load schedule %s: %s", path.name, e)

    return jobs


def _is_due(job: ScheduledJob, now: datetime) -> bool:
    """Check if a job should run at the current time."""
    cron = croniter(job.schedule, now)
    # Get the previous scheduled time
    prev = cron.get_prev(datetime)
    # If the previous scheduled time is within the last 60 seconds
    # and we haven't run it yet for that slot
    if (now - prev).total_seconds() < 60:
        if job.last_run is None or (prev - job.last_run).total_seconds() > 30:
            return True
    return False


def _run_job(job: ScheduledJob, agent, signal_client):
    """Execute a single scheduled job.

    If the job has a 'command' field, it calls the registered skill directly.
    Otherwise, it sends the prompt through the LLM agent.
    """
    logger.info("Running scheduled job: %s → %s", job.name, job.recipient)

    try:
        if job.command:
            # Direct tool invocation — bypass the LLM entirely
            from agent import get_registry
            registry = get_registry()
            cmd = job.command.lower() if job.command.startswith("/") else f"/{job.command.lower()}"

            if cmd not in registry.commands:
                reply = f"[Scheduled: {job.name}] Command '{cmd}' not found in registry."
            else:
                dc = registry.commands[cmd]
                if dc.arg_name and job.command_args:
                    result = dc.func(**{dc.arg_name: job.command_args})
                elif dc.arg_name:
                    result = dc.func(**{dc.arg_name: ""})
                else:
                    result = dc.func()
                reply = str(result) if result else "(no output)"
        else:
            # LLM agent invocation
            result = agent(job.prompt)
            reply = str(result)
    except Exception as e:
        logger.exception("Scheduled job '%s' failed", job.name)
        reply = f"[Scheduled: {job.name}] Error: {e}"

    signal_client.send(job.recipient, f"📅 {job.name}\n\n{reply}")
    logger.info("Scheduled job '%s' sent to %s (%d chars)", job.name, job.recipient, len(reply))


def start_scheduler(agent, signal_client):
    """Start the scheduler as a daemon thread.

    Args:
        agent: The Strands Agent instance.
        signal_client: The SignalClient for sending messages.
    """
    jobs = _load_jobs()
    if not jobs:
        logger.info("No scheduled jobs found in schedules/")
        return

    logger.info("Scheduler started with %d job(s)", len(jobs))

    def _loop():
        while True:
            try:
                now = datetime.now()
                for job in jobs:
                    if _is_due(job, now):
                        job.last_run = now
                        # Run in a separate thread so scheduler doesn't block
                        t = threading.Thread(
                            target=_run_job,
                            args=(job, agent, signal_client),
                            daemon=True,
                        )
                        t.start()
            except Exception:
                logger.exception("Scheduler tick error")

            time.sleep(30)  # check every 30 seconds

    thread = threading.Thread(target=_loop, daemon=True, name="scheduler")
    thread.start()
