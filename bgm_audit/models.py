from dataclasses import asdict, dataclass, field


@dataclass
class Detection:
    engine: str
    track_id: str
    title: str
    artist: str
    start: float
    end: float
    range_kind: str
    evidence: list[dict] = field(default_factory=list)
    identifiers: dict = field(default_factory=dict)
    status: str = "待核验"
    reason: str = "识别结果需与授权材料核对"
    license_snapshot: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class EngineError:
    engine: str
    kind: str
    message: str
    start: float | None = None
    end: float | None = None
    attempts: int = 1

    def to_dict(self):
        return asdict(self)
