import uuid
from pathlib import Path


class LocalTemporaryStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def new_key(self, suffix: str) -> str:
        return f"{uuid.uuid4().hex}{suffix}"

    def _resolve(self, key: str) -> Path:
        if Path(key).name != key:
            raise ValueError("Invalid storage key")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("Invalid storage key")
        return path

    def write(self, key: str, content: bytes) -> None:
        self._resolve(key).write_bytes(content)

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def path_for(self, key: str) -> Path:
        return self._resolve(key)

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str | None) -> None:
        if key is None:
            return
        path = self._resolve(key)
        path.unlink(missing_ok=True)
