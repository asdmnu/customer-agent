from langchain_core.tools import tool


@tool
def get_current_plan(phone_number: str) -> dict:
    """查询当前套餐。"""
    return {"success": True, "message": "查询当前套餐"}


@tool
def list_available_plans() -> dict:
    """查询可办理套餐。"""
    return {"success": True, "message": "查询可办理套餐"}


@tool
def check_plan_change_eligibility(phone_number: str, target_plan_code: str) -> dict:
    """检查套餐变更资格。"""
    return {"success": True, "message": "检查套餐变更资格"}


@tool
def change_plan(phone_number: str, target_plan_code: str, effective_mode: str) -> dict:
    """办理套餐变更。"""
    return {"success": True, "message": "办理套餐变更"}
