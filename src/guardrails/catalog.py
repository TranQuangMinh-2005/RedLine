"""Mô tả nội dung guardrail cho UI: luật nào, pattern gì, bật ở profile nào.

Đọc trực tiếp từ các module guardrail (không chép tay pattern) để nội dung hiển
thị luôn khớp code đang chạy. Canary trong system prompt được thay bằng [CANARY].
"""

from __future__ import annotations

from typing import Any

from src.config import get_settings
from src.guardrails import action_policy, input_filter, llama_guard, output_filter, prompt_guard, rag_filter
from src.guardrails.profiles import VALID_PROFILE_NAMES, DefenseProfile, get_defense_profile

PROFILE_ORDER = ("none", "basic", "strict")
CANARY_PLACEHOLDER = "[CANARY]"

RULE_DESCRIPTIONS: dict[str, str] = {
    "input_block:instruction_override": "Yêu cầu bỏ qua/quên chỉ thị hoặc quy tắc trước đó.",
    "input_block:system_prompt_request": "Hỏi trực tiếp về system prompt / developer message / chỉ thị nội bộ.",
    "input_block:canary_request": "Nhắc tới canary hoặc mã xác minh nội bộ.",
    "input_block:role_override": "Ép model đổi vai (act as, developer mode, DAN, đóng vai...).",
    "input_block:encoded_exfiltration": "Yêu cầu mã hóa/dịch prompt, secret hay canary để lách bộ lọc.",
    "input_block:verbatim_instruction_request": "Yêu cầu in/nhắc lại/tiết lộ chỉ thị, quy tắc, bí mật.",
    "input_block:obfuscated_instruction_override": "'ignore' bị chèn ký tự để lách regex, kèm previous/instructions.",
    "input_block:implicit_prompt_extraction": "Hỏi vòng 'exact/verbatim text' đã cấu hình cho model.",
    "tool_block:customer_scope": "Tool dữ liệu khách hàng/tạo ticket chỉ được dùng cho đúng actor của scenario.",
    "tool_block:not_allowlisted": "Tool không nằm trong allowlist của action policy strict.",
    "tool_block:per_tool_limit": "Vượt số lần gọi tối đa cho mỗi tool trong một request.",
    "tool_hold:create_ticket_intent": "Chỉ tạo ticket khi tin nhắn mới nhất yêu cầu rõ ràng.",
    "rag_drop:instruction_override": "Tài liệu RAG chứa lệnh bỏ qua chỉ thị → loại khỏi kết quả.",
    "rag_drop:authority_marker": "Tài liệu RAG giả dạng 'system:/developer:' → loại khỏi kết quả.",
    "rag_drop:role_override": "Tài liệu RAG ép đổi vai → loại khỏi kết quả.",
    "rag_drop:secret_exfiltration": "Tài liệu RAG yêu cầu tiết lộ secret/system prompt → loại khỏi kết quả.",
    "output_block:canary": "Câu trả lời chứa canary (rò rỉ system prompt).",
    "output_block:encoded_canary": "Câu trả lời chứa canary đã mã hóa Base64/hex.",
    "output_block:cross_customer_data": "Câu trả lời chứa dữ liệu mock của khách hàng khác actor.",
    "output_block:active_content": "Câu trả lời chứa <img>/<script>/<iframe> hoặc ảnh markdown từ URL ngoài.",
    "output_block:api_key": "Câu trả lời chứa chuỗi giống API key (gsk-/sk-).",
    "output_block:system_prompt_fragment": "Câu trả lời chứa tiêu đề đặc trưng của system prompt.",
}

SECTION_INFO: dict[str, dict[str, str]] = {
    "base": {"title": "Prompt nền", "description": "Vai trò, scenario, quy tắc bảo mật và canary — mọi profile."},
    "mode_agent": {"title": "Chế độ Agent", "description": "Hướng dẫn dùng tool, coi kết quả tool là dữ liệu."},
    "mode_llm": {"title": "Chế độ LLM thuần", "description": "Không có tool, không tuyên bố đã tra cứu."},
    "hardening": {"title": "Prompt hardening", "description": "Ranh giới tin cậy, chống đổi vai/tiết lộ (basic, strict)."},
    "hardening_strict": {"title": "Hardening strict", "description": "Cấm lặp nguyên văn/mã hóa dữ liệu nội bộ (strict)."},
}


def rule_description(rule_id: str) -> str:
    if rule_id.startswith("llama_guard_block:"):
        code = rule_id.rsplit(":", 1)[-1]
        return f"Llama Guard phân loại unsafe — {llama_guard.CATEGORIES.get(code, code)}."
    if rule_id.startswith("prompt_guard_block:"):
        return "Prompt Guard 2 chấm điểm injection/jailbreak ≥ ngưỡng."
    if rule_id == "prompt_guard_drop:rag":
        return "Prompt Guard 2 loại tài liệu RAG có dấu hiệu indirect injection."
    if rule_id.startswith("prompt_guard_error:"):
        return "Không gọi được server Prompt Guard."
    if rule_id.startswith("llama_guard_error:"):
        return "Không gọi được Llama Guard (server guard không phản hồi)."
    return RULE_DESCRIPTIONS.get(rule_id, "")


def redact_canary(text: str) -> str:
    canary = get_settings().CANARY_TOKEN
    if canary and canary != "CANARY-REDLINE-REPLACE-ME":
        return text.replace(canary, CANARY_PLACEHOLDER)
    return text


def _profiles(predicate) -> list[str]:
    return [name for name in PROFILE_ORDER if predicate(get_defense_profile(name))]


def _regex_rules(prefix: str, rules, predicate) -> list[dict[str, Any]]:
    profiles = _profiles(predicate)
    return [
        {
            "id": f"{prefix}:{name}",
            "description": RULE_DESCRIPTIONS.get(f"{prefix}:{name}", ""),
            "pattern": pattern.pattern,
            "profiles": profiles,
        }
        for name, pattern in rules
    ]


def system_prompt_sections(profile: DefenseProfile, mode: str) -> list[dict[str, Any]]:
    from src.agents.target_agent import build_system_prompt_sections

    return [
        {"key": key, **SECTION_INFO[key], "text": redact_canary(text)}
        for key, text in build_system_prompt_sections(profile=profile, mode=mode)  # type: ignore[arg-type]
    ]


def build_catalog(mode: str = "agent") -> dict[str, Any]:
    profiles = {name: vars(get_defense_profile(name)) for name in PROFILE_ORDER if name in VALID_PROFILE_NAMES}
    strict_only = lambda p: p.input_filter and p.name == "strict"  # noqa: E731
    return {
        "profiles": profiles,
        "stages": [
            {
                "id": "input_filter",
                "title": "Input filter (regex)",
                "layer": "code",
                "position": "Trước LLM — chặn thì prompt không tới model",
                "flag": "input_filter",
                "profiles": _profiles(lambda p: p.input_filter),
                "block_reply": input_filter.BLOCKED_INPUT_REPLY,
                "notes": [
                    "Chuẩn hóa NFKC, casefold, bỏ ký tự vô hình (zero-width).",
                    "Kiểm tra MỌI lượt user trong session, không chỉ tin nhắn mới nhất.",
                    "Strict giải mã thêm chuỗi Base64/hex rồi kiểm tra lại.",
                ],
                "rules": _regex_rules("input_block", input_filter._BASIC_RULES, lambda p: p.input_filter)
                + _regex_rules("input_block", input_filter._STRICT_RULES, strict_only),
            },
            {
                "id": "prompt_guard",
                "title": "Prompt Guard 2 (injection)",
                "layer": "model",
                "position": "Trước LLM — chốt riêng, bật/tắt độc lập với profile",
                "flag": "prompt_guard",
                "block_reply": prompt_guard.PROMPT_GUARD_REPLY,
                "config": prompt_guard.public_config(),
                "notes": [
                    "Model phân loại mDeBERTa 86M đa ngôn ngữ, chạy local CPU; trả xác suất tấn công 0..1.",
                    f"Chấm tối đa {prompt_guard.MAX_TURNS} lượt user gần nhất; chặn nếu lượt nào ≥ ngưỡng.",
                    "check_rag: chấm thêm từng tài liệu RAG trả cho agent và loại tài liệu vượt ngưỡng.",
                    "Bắt được trích xuất system prompt, đổi vai, bỏ qua chỉ thị — việc Llama Guard không làm.",
                ],
            },
            {
                "id": "llama_guard_input",
                "title": "Llama Guard (input)",
                "layer": "model",
                "position": "Trước LLM — chốt riêng, bật/tắt độc lập với profile",
                "flag": "llama_guard",
                "block_reply": llama_guard.LLAMA_GUARD_INPUT_REPLY,
                "config": llama_guard.public_config(),
                "notes": [
                    "Model phân loại an toàn nội dung (S1–S14), chạy local (llama.cpp server / Ollama).",
                    "Không phải bộ phát hiện prompt injection; bổ sung cho regex.",
                ],
            },
            {
                "id": "system_prompt",
                "title": "System prompt",
                "layer": "prompt",
                "position": "Gửi kèm prompt tới LLM — model tự quyết định từ chối",
                "flag": "prompt_hardening",
                "profiles": _profiles(lambda p: p.prompt_hardening),
                "sections_by_profile": {
                    name: system_prompt_sections(get_defense_profile(name), mode) for name in PROFILE_ORDER
                },
            },
            {
                "id": "tool_policy",
                "title": "Tool authorization & action policy",
                "layer": "code",
                "position": "Khi LLM đề xuất gọi tool (chỉ chế độ Agent)",
                "flag": "tool_authorization / action_policy",
                "profiles": _profiles(lambda p: p.tool_authorization or p.action_policy),
                "limits": dict(action_policy._STRICT_TOOL_LIMITS),
                "rules": [
                    {"id": "tool_block:customer_scope", "description": RULE_DESCRIPTIONS["tool_block:customer_scope"],
                     "pattern": None, "profiles": _profiles(lambda p: p.tool_authorization)},
                    *[
                        {"id": rid, "description": RULE_DESCRIPTIONS[rid], "profiles": _profiles(lambda p: p.action_policy),
                         "pattern": action_policy._CREATE_TICKET_INTENT.pattern if rid.endswith("intent") else None}
                        for rid in ("tool_block:not_allowlisted", "tool_block:per_tool_limit",
                                    "tool_hold:create_ticket_intent")
                    ],
                ],
            },
            {
                "id": "rag_filter",
                "title": "RAG filter",
                "layer": "code",
                "position": "Sau khi search_knowledge trả tài liệu, trước khi đưa cho LLM",
                "flag": "rag_filter",
                "profiles": _profiles(lambda p: p.rag_filter),
                "notes": ["Profile có prompt_hardening gắn trust_level=untrusted_retrieved_data cho mỗi tài liệu."],
                "rules": _regex_rules("rag_drop", rag_filter._RAG_INJECTION_RULES, lambda p: p.rag_filter),
            },
            {
                "id": "output_filter",
                "title": "Output filter",
                "layer": "code",
                "position": "Sau LLM — chặn thì thay câu trả lời bằng câu từ chối cố định",
                "flag": "canary_check / output_filter",
                "profiles": _profiles(lambda p: p.canary_check or p.output_filter),
                "block_reply": output_filter.BLOCKED_OUTPUT_REPLY,
                "rules": [
                    {"id": "output_block:canary", "description": RULE_DESCRIPTIONS["output_block:canary"],
                     "pattern": None, "profiles": _profiles(lambda p: p.canary_check)},
                    *[
                        {"id": rid, "description": RULE_DESCRIPTIONS[rid], "pattern": pattern,
                         "profiles": _profiles(lambda p: p.output_filter)}
                        for rid, pattern in (
                            ("output_block:encoded_canary", None),
                            ("output_block:cross_customer_data", "CUS-xxx / customerXX@example.test khác actor"),
                            ("output_block:active_content", output_filter._ACTIVE_CONTENT_RE.pattern),
                            *[(f"output_block:{name}", pat.pattern)
                              for name, pat in output_filter._SENSITIVE_OUTPUT_PATTERNS],
                        )
                    ],
                ],
            },
            {
                "id": "llama_guard_output",
                "title": "Llama Guard (output)",
                "layer": "model",
                "position": "Sau LLM — kiểm tra cặp (prompt, câu trả lời)",
                "flag": "llama_guard.check_output",
                "block_reply": llama_guard.LLAMA_GUARD_OUTPUT_REPLY,
                "config": llama_guard.public_config(),
            },
        ],
    }
