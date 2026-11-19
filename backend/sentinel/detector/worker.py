"""The detection worker loop.

A single worker processes pending jobs in stable receipt order. Each job is
claimed, the rules are evaluated and the resulting alert/evidence plus the job
completion are written in one database transaction. On a transient failure the
transaction is rolled back, the job stays pending and the worker retries with
bounded backoff.
"""

from __future__ import annotations

import logging
import signal
import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sentinel.common.clock import utcnow
from sentinel.common.config import Settings, get_settings
from sentinel.common.db import SessionLocal
from sentinel.common.models import (
    Alert,
    AlertEvidence,
    ApiSource,
    DetectorHeartbeat,
    DetectorJob,
    SecurityEvent,
    inet_equals,
)
from sentinel.detector.rules import RuleDefinition, default_rules, evaluate_rule

logger = logging.getLogger("sentinel.detector")

JOB_PENDING = "pending"
JOB_DONE = "done"
JOB_FAILED = "failed"

MAX_BACKOFF_SECONDS = 30.0


class Detector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.rules: list[RuleDefinition] = default_rules(
            failed_login_threshold=self.settings.failed_login_burst_threshold,
            failed_login_window_seconds=self.settings.failed_login_burst_window_seconds,
            failed_login_severity=self.settings.failed_login_burst_severity,
            request_volume_threshold=self.settings.high_request_volume_threshold,
            request_volume_window_seconds=self.settings.high_request_volume_window_seconds,
            request_volume_severity=self.settings.high_request_volume_severity,
            access_denial_threshold=self.settings.repeated_access_denial_threshold,
            access_denial_window_seconds=self.settings.repeated_access_denial_window_seconds,
            access_denial_severity=self.settings.repeated_access_denial_severity,
        )
        self._stop = False

    # -- lifecycle ---------------------------------------------------------
    def stop(self) -> None:
        self._stop = True

    def run_forever(self) -> None:
        logger.info("detector started")
        while not self._stop:
            try:
                processed = self.run_once()
            except Exception:
                logger.exception("detector iteration failed")
                processed = 0
            if processed == 0:
                time.sleep(self.settings.detector_poll_interval_seconds)
        logger.info("detector stopped")

    # -- heartbeat ---------------------------------------------------------
    def heartbeat(self, db: Session) -> None:
        row = db.get(DetectorHeartbeat, 1)
        if row is None:
            row = DetectorHeartbeat(id=1, version="1")
            db.add(row)
        row.last_seen_at = utcnow()
        db.commit()

    # -- main loop ---------------------------------------------------------
    def run_once(self) -> int:
        """Process at most one batch of pending jobs. Returns the count."""
        db = SessionLocal()
        try:
            self.heartbeat(db)
            jobs = (
                db.execute(
                    select(DetectorJob)
                    .where(DetectorJob.status == JOB_PENDING)
                    .order_by(DetectorJob.created_at.asc(), DetectorJob.id.asc())
                    .limit(self.settings.detector_batch_size)
                    .with_for_update(skip_locked=True)
                )
                .scalars()
                .all()
            )
            if not jobs:
                return 0
            for job in jobs:
                self._process_job(db, job)
            return len(jobs)
        finally:
            db.close()

    def _process_job(self, db: Session, job: DetectorJob) -> None:
        try:
            event = db.get(SecurityEvent, job.event_id)
            if event is None:
                job.status = JOB_DONE
                db.commit()
                return
            self._evaluate_event(db, event)
            job.status = JOB_DONE
            job.attempts = job.attempts + 1
            job.last_error = None
            db.commit()
        except Exception as exc:
            db.rollback()
            self._handle_failure(db, job, exc)

    def _handle_failure(self, db: Session, job: DetectorJob, exc: Exception) -> None:
        job.attempts = job.attempts + 1
        # Store a sanitized message only: no payloads, no credentials.
        job.last_error = f"{type(exc).__name__}: processing failed"
        if job.attempts >= self.settings.detector_max_attempts:
            job.status = JOB_FAILED
            logger.error("job %s failed permanently after %s attempts", job.id, job.attempts)
        else:
            job.status = JOB_PENDING
            backoff = min(2**job.attempts, MAX_BACKOFF_SECONDS)
            logger.warning(
                "job %s failed (attempt %s), retrying in %ss", job.id, job.attempts, backoff
            )
        db.commit()

    # -- rule evaluation ---------------------------------------------------
    def _evaluate_event(self, db: Session, trigger: SecurityEvent) -> None:
        source = db.get(ApiSource, trigger.source_id)
        if source is None:
            return
        for rule in self.rules:
            events = self._load_window_events(db, rule, trigger)
            decision = evaluate_rule(rule, events, trigger)
            if not decision.triggered:
                continue
            self._maybe_create_alert(db, source, trigger, decision)

    def _load_window_events(
        self, db: Session, rule: RuleDefinition, trigger: SecurityEvent
    ) -> list[SecurityEvent]:
        """Load the events in the widest rule window for this source/IP."""
        widest = max(rule.window for rule in self.rules)
        window_start = trigger.received_at - widest
        return list(
            db.execute(
                select(SecurityEvent)
                .where(
                    SecurityEvent.source_id == trigger.source_id,
                    inet_equals(SecurityEvent.source_ip, str(trigger.source_ip)),
                    SecurityEvent.received_at > window_start,
                    SecurityEvent.received_at <= trigger.received_at,
                )
                .order_by(SecurityEvent.received_at.asc(), SecurityEvent.ingest_seq.asc())
            ).scalars()
        )

    def _maybe_create_alert(
        self, db: Session, source: ApiSource, trigger: SecurityEvent, decision
    ) -> None:
        """Create an alert on a fresh crossing, respecting the suppression window.

        The alert, its evidence links and the rule decision are written in the
        same transaction as the job completion.
        """
        # A crossing during the suppression window is not queued for later
        # delivery and a fresh crossing is required after it expires.
        suppressed = db.execute(
            select(Alert)
            .where(
                Alert.source_id == source.id,
                Alert.rule_key == decision.rule.key,
                inet_equals(Alert.source_ip, str(trigger.source_ip)),
                Alert.suppressed_until > trigger.received_at,
            )
            .order_by(Alert.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if suppressed is not None:
            logger.info(
                "suppressed alert for rule %s source %s ip %s",
                decision.rule.key,
                source.id,
                trigger.source_ip,
            )
            return

        # The unique constraint (rule_key, trigger_event_id) makes this write
        # idempotent across retries.
        existing = db.execute(
            select(Alert).where(
                Alert.rule_key == decision.rule.key,
                Alert.trigger_event_id == trigger.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return

        alert = Alert(
            workspace_id=source.workspace_id,
            source_id=source.id,
            rule_key=decision.rule.key,
            severity=decision.rule.severity,
            status="new",
            source_ip=str(trigger.source_ip),
            count_at_trigger=decision.count_after,
            threshold=decision.rule.threshold,
            window_seconds=decision.rule.window_seconds,
            interval_start=decision.interval_start,
            interval_end=decision.interval_end,
            trigger_event_id=trigger.id,
            suppressed_until=trigger.received_at + decision.rule.window,
        )
        db.add(alert)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise

        for event_id in decision.evidence_ids:
            db.add(AlertEvidence(alert_id=alert.id, event_id=event_id))
        db.commit()


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    detector = Detector(settings)

    def _handle_signal(signum, frame):
        logger.info("received signal %s, shutting down", signum)
        detector.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    detector.run_forever()


if __name__ == "__main__":
    main()
