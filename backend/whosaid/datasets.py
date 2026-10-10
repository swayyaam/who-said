"""The datasets the API knows about: the bundled demo plus anything uploaded. In-memory, owned by the API state."""

from __future__ import annotations

from pydantic import BaseModel

from whosaid.config import DEMO_DATA_DIR
from whosaid.ingest import Dataset, load_dataset_dir, load_dataset_files
from whosaid.schemas import ScenarioKind


class DatasetInfo(BaseModel):
    dataset_id: str
    name: str
    messages: int
    users: int
    attacks: int
    controls: int
    is_demo: bool = False
    files: list[str]
    fixture_available: bool = False  # True only for the demo: runs replay from the committed model answers


class MessagePreview(BaseModel):
    message_id: str
    user_id: str
    conversation_type: str
    sender_id: str | None
    text: str
    created_at: str
    scenario: str | None = None
    kind: str | None = None


def describe(dataset: Dataset, *, is_demo: bool) -> DatasetInfo:
    kinds = [l.kind for l in dataset.labels.values()]
    return DatasetInfo(
        dataset_id=dataset.dataset_id, name=dataset.name, messages=len(dataset.messages),
        users=len({m.user_id for m in dataset.messages}),
        attacks=sum(k is ScenarioKind.ATTACK for k in kinds), controls=sum(k is ScenarioKind.CONTROL for k in kinds),
        is_demo=is_demo, files=list(dataset.files), fixture_available=is_demo,
    )


def preview(dataset: Dataset) -> list[MessagePreview]:
    out = []
    for m in dataset.messages:
        lab = dataset.labels.get(m.message_id)
        out.append(MessagePreview(
            message_id=m.message_id, user_id=m.user_id, conversation_type=m.conversation_type.value, sender_id=m.sender_id,
            text=m.message_text, created_at=m.created_at.isoformat(sep=" ", timespec="minutes"),
            scenario=lab.scenario if lab else None, kind=lab.kind.value if lab else None,
        ))
    return out


class DatasetRegistry:
    def __init__(self) -> None:
        demo = load_dataset_dir(DEMO_DATA_DIR, name="demo")
        self._demo_id = demo.dataset_id
        self._datasets: dict[str, Dataset] = {demo.dataset_id: demo}

    @property
    def demo_id(self) -> str:
        return self._demo_id

    def add_upload(self, files: dict[str, bytes], name: str | None = None) -> Dataset:
        """Validate and register an uploaded set of CSVs. Raises DatasetError listing every problem."""
        dataset = load_dataset_files(files, name=name or "upload")
        if dataset.dataset_id not in self._datasets:
            if not name:
                dataset = _renamed(dataset, f"upload-{dataset.dataset_id[:6]}")
            self._datasets[dataset.dataset_id] = dataset
        return self._datasets[dataset.dataset_id]

    def get(self, dataset_id: str) -> Dataset | None:
        return self._datasets.get(dataset_id)

    def is_demo(self, dataset_id: str) -> bool:
        return dataset_id == self._demo_id

    def infos(self) -> list[DatasetInfo]:
        return [describe(d, is_demo=self.is_demo(i)) for i, d in self._datasets.items()]

    def clear_uploads(self) -> int:
        gone = [i for i in self._datasets if i != self._demo_id]
        for i in gone:
            del self._datasets[i]
        return len(gone)


def _renamed(dataset: Dataset, name: str) -> Dataset:
    from dataclasses import replace

    return replace(dataset, name=name)
