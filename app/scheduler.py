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
    # Optional: override model for this job (e.g. a smaller/faster model)
    model: str | None = None
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
                    model=data.get("model"),
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


MAX_JOB_RETRIES = 3
JOB_RETRY_DELAY = 15  # seconds between retries


def _run_job(job: ScheduledJob, agent, signal_client):
    """Execute a single scheduled job with retries.

    If the job has a 'command' field, it calls the registered skill directly.
    Otherwise, it sends the prompt through the LLM agent.
    If the job specifies a 'model', a dedicated agent is created for it.
    Retries up to MAX_JOB_RETRIES times on failure (gives LLM server time to load).
    """
    logger.info("Running scheduled job: %s → %s", job.name, job.recipient)

    # Warm up: ensure the model is loaded before running the job
    from agent import ensure_model_loaded
    ensure_model_loaded(job.model)

    for attempt in range(1, MAX_JOB_RETRIES + 1):
        try:
            if job.command:
                from agent import get_registry
                registry = get_registry()
                cmd = job.command.lower() if job.command.startswith("/") else f"/{job.command.lower()}"

                if cmd not in registry.commands:
                    reply = f"[Scheduled: {job.name}] Command '{cmd}' not found in registry."
                    break
                dc = registry.commands[cmd]
                if dc.arg_name and job.command_args:
                    result = dc.func(**{dc.arg_name: job.command_args})
                elif dc.arg_name:
                    result = dc.func(**{dc.arg_name: ""})
                else:
                    result = dc.func()
                reply = str(result) if result else "(no output)"
            else:
                job_agent = agent
                if job.model:
                    from strands import Agent
                    from strands.models.openai import OpenAIModel
                    import config
                    model = OpenAIModel(
                        client_args={
                            "base_url": config.llm.base_url,
                            "api_key": config.llm.api_key,
                        },
                        model_id=job.model,
                        params={
                            "temperature": config.llm.temperature,
                            "max_tokens": config.llm.max_tokens,
                        },
                    )
                    job_agent = Agent(model=model, system_prompt="You are a helpful assistant. Use plain text for outputs (no markdown) and avoid using markdown-like symbols (asterisks for bold, hashes for sections etc.).")
                    logger.info("Job '%s' using model override: %s", job.name, job.model)

                result = job_agent(job.prompt)
                reply = str(result)

            # Success — break out of retry loop
            break

        except Exception as e:
            logger.warning("Scheduled job '%s' attempt %d/%d failed: %s",
                           job.name, attempt, MAX_JOB_RETRIES, e)
            if attempt < MAX_JOB_RETRIES:
                time.sleep(JOB_RETRY_DELAY)
            else:
                logger.exception("Scheduled job '%s' failed after %d attempts", job.name, MAX_JOB_RETRIES)
                reply = f"[Scheduled: {job.name}] Error after {MAX_JOB_RETRIES} attempts: {e}"

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
