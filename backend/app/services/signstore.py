"""签文库:加载 data/lvzu_signs.json,进程内只读缓存。"""
import json
import secrets
from typing import Any

from ..config import DATA_PATH


class SignStore:
    def __init__(self, path=DATA_PATH) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.meta: dict[str, Any] = payload["meta"]
        self._signs: list[dict[str, Any]] = payload["signs"]
        self._by_no: dict[int, dict[str, Any]] = {s["no"]: s for s in self._signs}
        if len(self._by_no) != 100:
            raise RuntimeError(f"签文库数据异常:期望 100 签,实际 {len(self._by_no)}")

    @property
    def total(self) -> int:
        return len(self._signs)

    def list_brief(self) -> list[dict[str, Any]]:
        return [
            {"no": s["no"], "title": s["title"], "ancient": s["ancient"], "lucky": s.get("lucky")}
            for s in self._signs
        ]

    def get(self, no: int) -> dict[str, Any] | None:
        return self._by_no.get(no)

    def random_no(self) -> int:
        """安全随机抽签 1-100(随机性不经过任何外部服务)。"""
        return secrets.randbelow(self.total) + 1


store = SignStore()
