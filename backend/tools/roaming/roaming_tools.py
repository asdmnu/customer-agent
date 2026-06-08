from langchain_core.tools import tool


@tool
def check_roaming_eligibility(phone_number: str, destination: str) -> dict:
    """检查国际漫游开通资格。"""
    return {"success": True, "message": "检查国际漫游开通资格"}


@tool
def list_roaming_packages(destination: str) -> dict:
    """查询国际漫游套餐。"""
    return {"success": True, "message": "查询国际漫游套餐"}


@tool
def enable_roaming(
    phone_number: str,
    destination: str,
    plan_code: str,
    customer_confirmed: bool,
) -> dict:
    """办理国际漫游开通。"""
    return {"success": True, "message": "办理国际漫游开通"}
