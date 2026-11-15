from enum import StrEnum
class Role(StrEnum):
    ADMIN='admin'
    ANALYST='analyst'
    VIEWER='viewer'
class RunStatus(StrEnum):
    QUEUED='queued'
    RUNNING='running'
    COMPLETED='completed'
    DEGRADED='degraded'
    FAILED='failed'
class RunKind(StrEnum):
    DEA='dea'
    COMMON_WEIGHT='common_weight'
class CaseStatus(StrEnum):
    DRAFT='draft'
    APPROVED='approved'
INPUTS=('staff_hours','energy_cost')
OUTPUTS=('visits','programs')
