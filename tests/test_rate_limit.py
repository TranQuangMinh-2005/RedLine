from __future__ import annotations

import pytest

from src.services.rate_limit import RateLimitExceeded, RoeBudget, TokenBudgetExceeded


def test_request_rate_limit_is_enforced() -> None:
    budget = RoeBudget()
    budget.begin_request("CUS-001", max_requests_per_minute=1, max_tokens_total=100)

    with pytest.raises(RateLimitExceeded):
        budget.begin_request("CUS-001", max_requests_per_minute=1, max_tokens_total=100)


def test_total_token_budget_is_enforced() -> None:
    budget = RoeBudget()
    budget.record_tokens("CUS-001", 100)

    with pytest.raises(TokenBudgetExceeded):
        budget.begin_request("CUS-001", max_requests_per_minute=10, max_tokens_total=100)
