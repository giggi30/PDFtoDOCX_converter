from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class JobPhase(StrEnum):
    VALIDATING = "VALIDATING"
    EXTRACTING = "EXTRACTING"
    ANALYZING_LAYOUT = "ANALYZING_LAYOUT"
    BUILDING_DOCX = "BUILDING_DOCX"
    RENDERING = "RENDERING"
    COMPARING = "COMPARING"


TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.EXPIRED,
}

_PHASE_ORDER = list(JobPhase)


class InvalidJobTransition(ValueError):
    pass


def validate_transition(
    current_status: JobStatus,
    current_phase: JobPhase | None,
    target_status: JobStatus,
    target_phase: JobPhase | None,
) -> None:
    if target_status is JobStatus.EXPIRED and current_status is not JobStatus.EXPIRED:
        return
    if current_status in TERMINAL_STATUSES:
        raise InvalidJobTransition(f"Cannot transition from terminal state {current_status}")
    if current_status is JobStatus.QUEUED:
        allowed = (
            target_status is JobStatus.PROCESSING and target_phase is JobPhase.VALIDATING
        ) or target_status in {JobStatus.FAILED, JobStatus.CANCELLED}
        if not allowed:
            raise InvalidJobTransition("Queued jobs must begin validation")
        return
    if current_status is JobStatus.PROCESSING:
        if target_status in {JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED}:
            if target_status is JobStatus.COMPLETED and current_phase is not JobPhase.COMPARING:
                raise InvalidJobTransition("A job can complete only after comparison")
            return
        if (
            target_status is JobStatus.PROCESSING
            and current_phase
            and target_phase
            and _PHASE_ORDER.index(target_phase) == _PHASE_ORDER.index(current_phase) + 1
        ):
            return
    raise InvalidJobTransition(
        f"Invalid transition {current_status}:{current_phase} -> {target_status}:{target_phase}"
    )


def progress_for(status: JobStatus, phase: JobPhase | None) -> int:
    if status is JobStatus.QUEUED:
        return 0
    if status is JobStatus.COMPLETED:
        return 100
    if status in TERMINAL_STATUSES:
        return 0
    if phase is None:
        return 0
    return {phase_value: (index + 1) * 15 for index, phase_value in enumerate(_PHASE_ORDER)}[phase]
