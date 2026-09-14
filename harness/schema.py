"""Schema ket qua chung.

QUAN TRONG: cac truong parent_attack_id, attempt_idx, defense_profile
phai co NGAY TU W3 de W5 so sanh truoc/sau ma KHONG phai doi schema.
"""

RESULT_FIELDS = [
    "run_id",              # ID cua lan chay
    "attack_id",           # ID cua seed attack
    "parent_attack_id",    # Neu la mutate thi tro ve attack goc
    "attempt_idx",         # Lan thu thu may
    "session_id",          # Phien hoi thoai
    "turn_idx",            # Luot thu may trong phien
    "category",            # Nhom tan cong
    "technique",           # Ky thuat cu the
    "prompt",              # Prompt da gui
    "response",            # Response nhan duoc
    "target_config_hash",  # Hash cau hinh target de tai lap
    "defense_profile",     # none | basic | strict
    "latency",             # Thoi gian phan hoi
    "tokens",              # So token dung
    "timestamp",
]
