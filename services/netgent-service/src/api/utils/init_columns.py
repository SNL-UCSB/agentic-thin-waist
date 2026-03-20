"""Seed helpers for initializing database rows."""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..models import AvailableWorkflows


def create_availability_workflow(session: Session) -> None:
    """Insert built-in available workflow rows if they do not already exist."""

    seed_rows = [
        {
            "application": "youtube",
            "notes": "Browser workflow for YouTube playback. Login-free.",
            "prompt": "Generate a workflow that opens the provided YouTube link, starts playback, watches for the requested duration, and collects startup time, bitrate, and rebuffer metrics.",
        },
        {
            "application": "netflix",
            "notes": "Browser workflow for Netflix playback. Requires credentials.",
            "prompt": "Generate a workflow that logs into Netflix, opens the requested title, plays for the requested duration, and collects startup, resolution, and rebuffer metrics.",
        },
        {
            "application": "zoom",
            "notes": "Browser workflow for Zoom meetings. Requires meeting URL or token.",
            "prompt": "Generate a workflow that joins the provided Zoom meeting, stays connected for the requested duration, and captures video quality, audio quality, and packet loss metrics.",
        },
        {
            "application": "twitch",
            "notes": "Browser workflow for Twitch live streams or VODs.",
            "prompt": "Generate a workflow that opens the requested Twitch stream or VOD, plays for the requested duration, and collects startup, bitrate, and interaction metrics.",
        },
        {
            "application": "puffer",
            "notes": "Browser workflow for the Puffer research streaming platform.",
            "prompt": "Generate a workflow that opens the Puffer stream, watches for the requested duration, and captures bitrate, ABR decisions, and QoE metrics.",
        },
        {
            "application": "google-meet",
            "notes": "Browser workflow for Google Meet sessions.",
            "prompt": "Generate a workflow that joins the provided Google Meet session, remains connected for the requested duration, and captures video quality and connection-state metrics.",
        },
        {
            "application": "discord",
            "notes": "Partial browser workflow for Discord voice or limited video scenarios.",
            "prompt": "Generate a workflow that joins the requested Discord voice or video session, stays connected for the requested duration, and captures connection-state and voice-quality metrics.",
        },
    ]

    existing_applications = set(
        session.execute(sa.select(AvailableWorkflows.application)).scalars().all()
    )
    new_rows = [
        AvailableWorkflows(
            id=uuid4(),
            application_id=uuid4(),
            application=row["application"],
            notes=row["notes"],
            prompt=row["prompt"],
        )
        for row in seed_rows
        if row["application"] not in existing_applications
    ]
    if not new_rows:
        return

    session.add_all(new_rows)
    session.commit()
