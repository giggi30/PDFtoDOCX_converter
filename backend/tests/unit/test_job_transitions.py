import pytest

from app.domain.jobs import InvalidJobTransition, JobPhase, JobStatus, validate_transition


def test_happy_path_requires_ordered_phases() -> None:
    validate_transition(JobStatus.QUEUED, None, JobStatus.PROCESSING, JobPhase.VALIDATING)
    validate_transition(
        JobStatus.PROCESSING,
        JobPhase.VALIDATING,
        JobStatus.PROCESSING,
        JobPhase.EXTRACTING,
    )
    validate_transition(JobStatus.PROCESSING, JobPhase.COMPARING, JobStatus.COMPLETED, None)


def test_skipping_a_phase_is_rejected() -> None:
    with pytest.raises(InvalidJobTransition):
        validate_transition(
            JobStatus.PROCESSING,
            JobPhase.VALIDATING,
            JobStatus.PROCESSING,
            JobPhase.BUILDING_DOCX,
        )


def test_completed_job_cannot_restart() -> None:
    with pytest.raises(InvalidJobTransition):
        validate_transition(JobStatus.COMPLETED, None, JobStatus.PROCESSING, JobPhase.VALIDATING)


def test_any_non_expired_job_can_expire() -> None:
    validate_transition(JobStatus.COMPLETED, None, JobStatus.EXPIRED, None)
