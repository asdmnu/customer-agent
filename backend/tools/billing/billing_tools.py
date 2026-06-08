from langchain_core.tools import tool


@tool
def query_current_bill(phone_number: str) -> dict:
    """查询当前账单。"""
    return {"success": True, "message": "查询当前账单"}


@tool
def query_bill_history(phone_number: str) -> dict:
    """查询历史账单。"""
    return {"success": True, "message": "查询历史账单"}


@tool
def query_balance_status(phone_number: str) -> dict:
    """查询余额状态。"""
    return {"success": True, "message": "查询余额状态"}
