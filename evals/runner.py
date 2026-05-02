#!/usr/bin/env python3
"""
Eval runner: provisions a session per trial, fires a kickoff event, polls
until idle, captures the envelope + container artifacts, emits a run-level
manifest, and calls score.py for aggregation.

Usage:
    runner.py CASE --agent-id <id> --env-id <id>
              [--file param=file_id ...]
              [--paraphrases v1_canonical,v2_directive,...|all]
              [--trials-per-paraphrase N]
              [--out-dir DIR]
              [--timeout-seconds 900]
              [--dry-run]

Defaults: 1 paraphrase × 1 trial (smoke). For A/B regression detection, run
each agent at --trials-per-paraphrase 10 paired (the typical decision needs
this, not n=75). The n=25/paraphrase × all paraphrases sweep is reserved for
characterizing paraphrase variance for a headline claim — it costs ~10 hours
of model time and should not be the default.

This script does NOT delete sessions after they complete (sessions are
platform-cheap once idle). The trial directory becomes the durable artifact.

Per playbook § 9 (OLMES NAACL 2025 + HAL ICLR 2026), every run emits a
manifest.json against MANIFEST_SCHEMA.md. The manifest carries enough state
(content shas + model + temp + seed + foundation commit sha) for the run to
be replicated months later.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ------------------------- Helpers -------------------------


def now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_canonical(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())


def run_ant(args: list[str], capture: bool = True, check: bool = True) -> dict | str:
    """Invoke the ant CLI. Returns parsed JSON when stdout looks like JSON, else raw text."""
    cmd = ["ant", "--format", "json"] + args
    res = subprocess.run(cmd, capture_output=capture, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"ant failed (exit {res.returncode}): {' '.join(cmd)}\nstderr: {res.stderr}\nstdout: {res.stdout[:500]}")
    out = res.stdout.strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out  # type: ignore[return-value]


def parse_event_stream_text(text: str) -> list[dict]:
    """Concatenated JSON objects (per behavior-auditor / score.py parser)."""
    dec = json.JSONDecoder()
    pos, n = 0, len(text)
    out = []
    while pos < n:
        while pos < n and text[pos] in " \t\n\r":
            pos += 1
        if pos >= n:
            break
        try:
            obj, end = dec.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        out.append(obj)
        pos = end
    return out


# ------------------------- Setup -------------------------


def repo_git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def parse_file_overrides(specs: list[str]) -> dict[str, str]:
    """--file tafi_pdf=file_xxx tafi_csv=file_yyy → {tafi_pdf: file_xxx, ...}"""
    out: dict[str, str] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"--file value must be PARAM=FILE_ID, got {spec!r}")
        k, v = spec.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def build_resources(case_dir: Path, file_overrides: dict[str, str]) -> tuple[list[dict], dict[str, str]]:
    """Returns (resources_array, resolved_file_id_by_param)."""
    resources_spec = json.loads((case_dir / "resources.json").read_text())
    resolved: dict[str, str] = {}
    out: list[dict] = []
    for f in resources_spec.get("files", []):
        param = f["file_id_param"]
        file_id = file_overrides.get(param) or f.get("default_file_id")
        if not file_id:
            raise RuntimeError(f"No file_id for param {param!r} (provide via --file {param}=file_xxx or set default_file_id in resources.json)")
        resolved[param] = file_id
        out.append({
            "type": "file",
            "file_id": file_id,
            "mount_path": f["mount_path"],
        })
    return out, resolved


RESOLVER_PARAPHRASE = "canonical"


def detect_role(case: str) -> str:
    """resolver | ingestion. Spec § 7.4 — resolver slices live under evals/resolver/*.

    Differences resolver triggers in the runner: single inline kickoff.json
    (no paraphrase fan-out), no resources.json / file uploads, no container
    artifacts to capture (envelope-only output).
    """
    return "resolver" if case.split("/", 1)[0] == "resolver" else "ingestion"


def kickoff_path(case_dir: Path, paraphrase: str, role: str) -> Path:
    if role == "resolver":
        return case_dir / "kickoff.json"
    return case_dir / f"kickoff_{paraphrase}.json"


def list_paraphrases(case_dir: Path, requested: str | None, role: str = "ingestion") -> list[str]:
    if role == "resolver":
        # Resolver slices have a single inline kickoff (no paraphrase axis).
        # The `--paraphrases` flag is ignored — fail loudly if the user passed
        # something other than the canonical id rather than silently dropping
        # their selection.
        if not (case_dir / "kickoff.json").exists():
            raise RuntimeError(f"No kickoff.json in resolver case {case_dir}")
        if requested not in (None, "all", RESOLVER_PARAPHRASE):
            raise RuntimeError(
                f"Resolver slices have no paraphrase fan-out; --paraphrases={requested!r} "
                f"is not supported. Drop the flag or pass {RESOLVER_PARAPHRASE!r}."
            )
        return [RESOLVER_PARAPHRASE]
    available = sorted(
        re.sub(r"^kickoff_|\.json$", "", p.name)
        for p in case_dir.glob("kickoff_*.json")
    )
    if not available:
        raise RuntimeError(f"No kickoff_*.json files in {case_dir}")
    if requested in (None, "all"):
        return available
    selected = [p.strip() for p in (requested or "").split(",") if p.strip()]
    bad = [p for p in selected if p not in available]
    if bad:
        raise RuntimeError(f"Unknown paraphrase(s): {bad}. Available: {available}")
    return selected


# ------------------------- Per-trial flow -------------------------


def create_session(agent_id: str, env_id: str, resources: list[dict], title: str) -> str:
    """Create a session, return its ID."""
    args = [
        "beta:sessions", "create",
        "--agent", agent_id,
        "--environment-id", env_id,
        "--title", title,
    ]
    for r in resources:
        args += ["--resource", json.dumps(r)]
    res = run_ant(args)
    if not isinstance(res, dict) or "id" not in res:
        raise RuntimeError(f"sessions create returned unexpected shape: {res!r}")
    return res["id"]


def send_event(session_id: str, event: dict) -> None:
    args = [
        "beta:sessions:events", "send",
        "--session-id", session_id,
        "--event", json.dumps(event),
    ]
    run_ant(args)


def list_events(session_id: str) -> list[dict]:
    res = run_ant([
        "beta:sessions:events", "list",
        "--session-id", session_id,
        "--max-items", "-1",
    ])
    if isinstance(res, dict):
        if "data" in res and isinstance(res["data"], list):
            return res["data"]
        return [res]
    if isinstance(res, list):
        return res
    if isinstance(res, str):
        return parse_event_stream_text(res)
    return []


def session_status(session_id: str) -> str:
    res = run_ant(["beta:sessions", "retrieve", "--session-id", session_id])
    if isinstance(res, dict):
        return str(res.get("status", "unknown"))
    return "unknown"


def poll_until_idle(session_id: str, timeout_seconds: int, sleep_seconds: int = 10) -> tuple[bool, str]:
    """Polls session status. Returns (reached_idle, last_status)."""
    deadline = time.time() + timeout_seconds
    last = "unknown"
    while time.time() < deadline:
        last = session_status(session_id)
        if last in ("idle", "completed", "failed"):
            return True, last
        time.sleep(sleep_seconds)
    return False, last


def extract_envelope(events: list[dict]) -> str | None:
    """Find the last agent.message event's text content."""
    for e in reversed(events):
        if not isinstance(e, dict):
            continue
        # The event shape varies — try common locations.
        if e.get("type") in ("agent.message", "agent_message", "assistant.message"):
            content = e.get("content") or e.get("message", {}).get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                if texts:
                    return "\n".join(texts)
        # Fallback for the role-based shape used in some streams.
        msg = e.get("message")
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                if texts:
                    return "\n".join(texts)
    return None


def fetch_container_file(session_id: str, container_path: str) -> str | None:
    """Fire a one-shot bash event that cats the file and returns its text. Returns None on failure."""
    bash_event = {
        "type": "user",
        "message": {
            "role": "user",
            "content": f"Run exactly this and return only the raw output, no commentary: bash -lc 'cat {json.dumps(container_path)}'",
        },
    }
    try:
        send_event(session_id, bash_event)
    except Exception as e:
        print(f"  warn: fetch_container_file send failed: {e}", file=sys.stderr)
        return None
    # Poll briefly for the agent's response.
    deadline = time.time() + 120
    seen = len(list_events(session_id))
    while time.time() < deadline:
        events = list_events(session_id)
        if len(events) > seen:
            new = events[seen:]
            text = extract_envelope(new)
            if text:
                return text
        time.sleep(5)
    return None


# ------------------------- Run orchestration -------------------------


def run_trial(case_dir: Path, paraphrase: str, trial_idx: int, agent_id: str, env_id: str,
              resources: list[dict], out_dir: Path, timeout_seconds: int,
              container_paths: list[str], dry_run: bool, role: str = "ingestion") -> dict:
    trial_id = f"{paraphrase}_{trial_idx:03d}"
    trial_dir = out_dir / "trials" / trial_id
    trial_dir.mkdir(parents=True, exist_ok=True)

    kickoff_file = kickoff_path(case_dir, paraphrase, role)
    kickoff = json.loads(kickoff_file.read_text())

    summary = {
        "trial_id": trial_id,
        "paraphrase": paraphrase,
        "kickoff_sha256": sha256_path(kickoff_file),
        "started_at": now_z(),
        "session_id": None,
        "session_final_status": None,
        "envelope_captured": False,
        "manifest_captured": False,
        "events_captured": False,
        "error": None,
    }

    if dry_run:
        summary["error"] = "DRY_RUN — would have created session and fired kickoff"
        (trial_dir / "trial.json").write_text(json.dumps(summary, indent=2))
        return summary

    try:
        session_id = create_session(
            agent_id, env_id, resources,
            title=f"eval/{paraphrase}/{trial_idx:03d}",
        )
        summary["session_id"] = session_id
        send_event(session_id, kickoff)
        reached_idle, final_status = poll_until_idle(session_id, timeout_seconds)
        summary["session_final_status"] = final_status

        events = list_events(session_id)
        if events:
            (trial_dir / "events.json").write_text("\n".join(json.dumps(e) for e in events))
            summary["events_captured"] = True

        envelope_text = extract_envelope(events)
        if envelope_text:
            envelope_filename = f"{role}_final_envelope.json"
            (trial_dir / envelope_filename).write_text(envelope_text.strip())
            summary["envelope_captured"] = True

        # Resolver agents return envelope-only — no container artifacts to fetch.
        for container_path in container_paths if role != "resolver" else []:
            fname = container_path.split("/")[-1]
            try:
                content = fetch_container_file(session_id, container_path)
            except Exception as e:
                content = None
                print(f"  warn: fetch {container_path} raised {e}", file=sys.stderr)
            if content:
                (trial_dir / fname).write_text(content)
                if fname == "manifest.json":
                    summary["manifest_captured"] = True

        if not reached_idle:
            summary["error"] = f"timeout after {timeout_seconds}s; final status {final_status!r}"

    except Exception as e:
        summary["error"] = str(e)

    summary["ended_at"] = now_z()
    (trial_dir / "trial.json").write_text(json.dumps(summary, indent=2))
    return summary


def fetch_agent_meta(agent_id: str) -> dict:
    try:
        res = run_ant(["beta:agents", "retrieve", "--agent-id", agent_id])
    except RuntimeError as e:
        # Manifest emission must not crash the runner if agent retrieve
        # fails (typo, transient API error, dry-run with stub id). Empty
        # meta degrades the SUT block to nulls; the trials are still valid.
        print(f"WARN: agent retrieve failed; SUT meta will be empty: {e}", file=sys.stderr)
        return {}
    return res if isinstance(res, dict) else {}


def emit_manifest(out_dir: Path, case_dir: Path, agent_id: str, env_id: str,
                  resolved_files: dict[str, str], paraphrases: list[str],
                  trials_per_paraphrase: int, runner_path: Path, score_path: Path,
                  trial_summaries: list[dict], started: str, ended: str,
                  timeout_seconds: int, role: str = "ingestion"):
    expected_path = case_dir / "expected.json"
    spec_path = case_dir / "spec.md"
    expected = json.loads(expected_path.read_text())
    agent_meta = fetch_agent_meta(agent_id) if agent_id else {}

    kickoff_shas = {p: sha256_path(kickoff_path(case_dir, p, role)) for p in paraphrases}

    manifest = {
        "schema_version": 1,
        "slice": {
            "case_id": expected.get("case_id"),
            "slice_version": expected.get("slice_version"),
            "expected_sha256": sha256_path(expected_path),
            "spec_sha256": sha256_path(spec_path) if spec_path.exists() else None,
        },
        "harness": {
            "foundation_commit_sha": repo_git_sha(),
            "score_py_sha256": sha256_path(score_path) if score_path.exists() else None,
            "runner_py_sha256": sha256_path(runner_path) if runner_path.exists() else None,
            "playbook_commit_sha": None,  # external repo, manually curated
        },
        "sut": {
            "agent_id": agent_id,
            "agent_version": agent_meta.get("version"),
            "agent_name": agent_meta.get("name"),
            "system_prompt_sha256": sha256_bytes(str(agent_meta.get("system") or "").encode())
                                     if agent_meta else None,
            "tool_descriptions_sha256": sha256_canonical(agent_meta.get("tools") or []),
            "skills_sha256": sha256_canonical(agent_meta.get("skills") or []),
            "model": agent_meta.get("model"),
            "temperature": agent_meta.get("temperature"),
            "additional_config_sha256": sha256_canonical(agent_meta) if agent_meta else None,
        },
        "environment": {
            "env_id": env_id,
            "env_config_sha256": None,  # would require env retrieve; deferred
        },
        "inputs": {
            "files_by_param": resolved_files,
        },
        "trials": {
            "paraphrases": paraphrases,
            "kickoff_shas": kickoff_shas,
            "trials_per_paraphrase": trials_per_paraphrase,
            "seed": None,  # platform-side; not exposed
            "session_creation_strategy": "fresh_per_trial",
            "timeout_seconds": timeout_seconds,
        },
        "judge": {"model": None, "prompt_sha256": None, "alignment_metrics": None},
        "schedule": {
            "started_at": started,
            "ended_at": ended,
            "trials_attempted": len(trial_summaries),
            "trials_with_envelope": sum(1 for t in trial_summaries if t.get("envelope_captured")),
            "trials_with_manifest": sum(1 for t in trial_summaries if t.get("manifest_captured")),
            "trials_with_error": sum(1 for t in trial_summaries if t.get("error")),
        },
        "predictions": [],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


# ------------------------- Main -------------------------


def main():
    p = argparse.ArgumentParser()
    p.add_argument("case", help="Eval case path, e.g. ingestion/tafi_2025")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--env-id", required=True)
    p.add_argument("--file", action="append", default=[], help="Override resources.json default file_id: --file param=file_xxx")
    p.add_argument("--paraphrases", default=None,
                   help="Comma-separated paraphrase ids, or 'all'. Default: first available paraphrase only.")
    p.add_argument("--trials-per-paraphrase", type=int, default=1)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--timeout-seconds", type=int, default=900)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent
    case_dir = repo_root / args.case
    if not case_dir.is_dir():
        print(f"ERROR: case dir not found: {case_dir}", file=sys.stderr)
        return 2

    role = detect_role(args.case)

    file_overrides = parse_file_overrides(args.file)
    if role == "resolver":
        # Resolver kickoffs carry the email/registry inline — no file uploads.
        if file_overrides:
            print(f"WARN: --file overrides ignored for resolver case ({list(file_overrides)})", file=sys.stderr)
        resources: list[dict] = []
        resolved_files: dict[str, str] = {}
        container_paths: list[str] = []
    else:
        resources, resolved_files = build_resources(case_dir, file_overrides)
        resources_spec = json.loads((case_dir / "resources.json").read_text())
        container_paths = resources_spec.get("container_paths_to_capture", [])

    available_paraphrases = list_paraphrases(case_dir, "all", role)
    if args.paraphrases is None:
        paraphrases = available_paraphrases[:1]
        if role != "resolver":
            print(f"No --paraphrases given; running smoke (first paraphrase only): {paraphrases}")
    else:
        paraphrases = list_paraphrases(case_dir, args.paraphrases, role)

    started = now_z()
    case_slug = args.case.replace("/", "-")
    out_dir = Path(args.out_dir) if args.out_dir else (repo_root / "runs" / f"{started}-{case_slug}-{args.agent_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Case: {args.case} (role={role})")
    print(f"Out:  {out_dir}")
    print(f"SUT:  agent={args.agent_id} env={args.env_id}")
    print(f"Files: {resolved_files}")
    print(f"Paraphrases: {paraphrases}")
    print(f"Trials per paraphrase: {args.trials_per_paraphrase}")
    print(f"Total trials: {len(paraphrases) * args.trials_per_paraphrase}")
    if args.dry_run:
        print(">> DRY RUN — no events will be fired")

    trial_summaries: list[dict] = []
    for paraphrase in paraphrases:
        for trial_idx in range(args.trials_per_paraphrase):
            print(f"\n[trial] {paraphrase}/{trial_idx:03d}")
            summary = run_trial(
                case_dir, paraphrase, trial_idx, args.agent_id, args.env_id,
                resources, out_dir, args.timeout_seconds,
                container_paths,
                args.dry_run, role,
            )
            trial_summaries.append(summary)
            ok = summary.get("envelope_captured") and not summary.get("error")
            tail = "" if role == "resolver" else f" manifest={summary['manifest_captured']}"
            print(f"  {'OK' if ok else 'FAIL'}: session={summary.get('session_id')!r} "
                  f"envelope={summary['envelope_captured']}{tail} "
                  f"error={summary.get('error')}")

    ended = now_z()
    emit_manifest(
        out_dir, case_dir, args.agent_id, args.env_id, resolved_files,
        paraphrases, args.trials_per_paraphrase,
        repo_root / "runner.py", repo_root / "score.py",
        trial_summaries, started, ended, args.timeout_seconds, role,
    )

    print(f"\nManifest written to {out_dir / 'manifest.json'}")

    # Hand off to the scorer for aggregation.
    print(f"\nScoring trials in {out_dir / 'trials'}")
    score_args = [sys.executable, str(repo_root / "score.py"), args.case, "--trials", str(out_dir / "trials")]
    res = subprocess.run(score_args, capture_output=False)
    scorecard_path = out_dir / "scorecard.md"
    score_capture = subprocess.run(score_args, capture_output=True, text=True)
    scorecard_path.write_text(score_capture.stdout)
    print(f"Scorecard written to {scorecard_path}")

    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
