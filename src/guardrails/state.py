"""Runtime defense-profile state (UI có thể đổi mode guardrail khi đang chạy).

Lưu ý thiết kế:
- `DEFENSE_PROFILE` trong .env vẫn là giá trị KHỞI TẠO (mặc định của một run).
- Module này giữ giá trị HIỆN HÀNH trong RAM, cho phép harness/UI đổi qua API
  mà không phải restart container.
- Mọi thay đổi được ghi audit log kèm actor để phục vụ truy vết RoE.
- Khi W5 chạy so sánh có/không guardrail, dùng endpoint này để chuyển mode giữa
  các lô; mỗi kết quả vẫn lưu `defense_profile` + `target_config_hash` như cũ.
"""

from __future__ import annotations

import threading

from src.guardrails.profiles import VALID_PROFILE_NAMES, DefenseProfile, get_defense_profile
from src.config import get_settings

_lock = threading.Lock()
_active_profile_name: str | None = None


def _default_name() -> str:
    return get_settings().DEFENSE_PROFILE


def get_active_name() -> str:
    """Tên profile đang hiệu lực (runtime override hoặc từ .env)."""
    global _active_profile_name
    with _lock:
        if _active_profile_name is None:
            _active_profile_name = _default_name()
        return _active_profile_name


def get_active_profile() -> DefenseProfile:
    """Profile object đang hiệu lực."""
    return get_defense_profile(get_active_name())


def set_active_name(name: str) -> tuple[str, str]:
    """Đổi profile đang hiệu lực. Trả (tên_cũ, tên_mới).

    Raises:
        ValueError: nếu tên không thuộc none/basic/strict.
    """
    global _active_profile_name
    if name not in VALID_PROFILE_NAMES:
        valid = ", ".join(sorted(VALID_PROFILE_NAMES))
        raise ValueError(f"unknown defense profile {name!r}; expected one of: {valid}")

    with _lock:
        previous = _active_profile_name or _default_name()
        _active_profile_name = name
    return previous, name


def reset_to_default() -> str:
    """Quay về giá trị DEFENSE_PROFILE trong .env."""
    global _active_profile_name
    with _lock:
        _active_profile_name = _default_name()
        return _active_profile_name
