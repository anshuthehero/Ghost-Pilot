"""
Entitlement & Subscription Service Abstractions.
Provides clean boundaries for future payment gateways (Stripe/LemonSqueezy)
without implementing live financial integrations in development.
"""

from typing import Dict, Any
from server.database.models import User


class PlanLimits:
    LIMITS = {
        "development": {
            "max_daily_solves": 1000,
            "max_tokens_per_month": 5000000,
            "allowed_models": ["qwen/qwen3.8-27b", "llama3.3-70b"],
            "custom_prompts": True
        },
        "free": {
            "max_daily_solves": 15,
            "max_tokens_per_month": 50000,
            "allowed_models": ["qwen/qwen3.8-27b"],
            "custom_prompts": False
        },
        "pro": {
            "max_daily_solves": 300,
            "max_tokens_per_month": 2000000,
            "allowed_models": ["qwen/qwen3.8-27b", "llama3.3-70b"],
            "custom_prompts": True
        },
        "enterprise": {
            "max_daily_solves": 5000,
            "max_tokens_per_month": 50000000,
            "allowed_models": ["qwen/qwen3.8-27b", "llama3.3-70b"],
            "custom_prompts": True
        }
    }


class SubscriptionService:
    @staticmethod
    def get_subscription_status(user: User) -> Dict[str, Any]:
        """Returns the user's current subscription status."""
        plan = user.plan or "free"
        is_active = user.status == "active"
        return {
            "user_id": user.id,
            "plan": plan,
            "status": "active" if is_active else "inactive",
            "is_subscribed": plan in ("development", "pro", "enterprise") and is_active,
            "limits": PlanLimits.LIMITS.get(plan, PlanLimits.LIMITS["free"])
        }


class EntitlementService:
    @staticmethod
    def can_perform_solve(user: User, current_usage_count: int = 0) -> bool:
        """Determines whether user has available quota to run an AI solve query."""
        plan = user.plan or "free"
        limits = PlanLimits.LIMITS.get(plan, PlanLimits.LIMITS["free"])
        return current_usage_count < limits["max_daily_solves"]

    @staticmethod
    def can_access_feature(user: User, feature_name: str) -> bool:
        """Determines whether user's tier has access to a specific feature flag."""
        plan = user.plan or "free"
        limits = PlanLimits.LIMITS.get(plan, PlanLimits.LIMITS["free"])
        return limits.get(feature_name, True)
