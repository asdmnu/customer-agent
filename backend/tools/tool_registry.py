"""按执行子场景返回受限工具集。"""

from backend.tools.billing.billing_tools import (
    query_balance_status,
    query_bill_history,
    query_current_bill,
)
from backend.tools.common.common_tools import (
    check_identity_status,
    create_handoff_ticket,
    lookup_customer_account,
    search_customer_policy,
)
from backend.tools.plan.plan_tools import (
    change_plan,
    check_plan_change_eligibility,
    get_current_plan,
    list_available_plans,
)
from backend.tools.roaming.roaming_tools import (
    check_roaming_eligibility,
    enable_roaming,
    list_roaming_packages,
)
from backend.tools.sim_service.sim_service_tools import (
    report_sim_loss,
    request_sim_replacement,
    restore_service,
)


TOOL_REGISTRY = {
    "roaming": [
        lookup_customer_account,
        check_roaming_eligibility,
        list_roaming_packages,
        enable_roaming,
        create_handoff_ticket,
        search_customer_policy,
    ],
    "plan_change": [
        lookup_customer_account,
        get_current_plan,
        list_available_plans,
        check_plan_change_eligibility,
        change_plan,
        create_handoff_ticket,
        search_customer_policy,
    ],
    "billing": [
        lookup_customer_account,
        query_current_bill,
        query_bill_history,
        query_balance_status,
        create_handoff_ticket,
        search_customer_policy,
    ],
    "sim_service": [
        lookup_customer_account,
        check_identity_status,
        report_sim_loss,
        restore_service,
        request_sim_replacement,
        create_handoff_ticket,
        search_customer_policy,
    ],
}


def get_tools_by_category(category: str) -> list:
    """获取指定执行子场景的工具列表。"""
    return TOOL_REGISTRY.get(category, [lookup_customer_account, create_handoff_ticket, search_customer_policy])
