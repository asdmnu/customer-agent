from langchain_core.tools import tool


@tool
def lookup_customer_account(phone_number: str) -> dict:
    """查询客户账户。"""
    return {"success": True, "message": "查询客户账户"}


@tool
def check_identity_status(phone_number: str) -> dict:
    """查询实名认证状态。"""
    return {"success": True, "message": "查询实名认证状态"}


@tool
def create_handoff_ticket(phone_number: str, issue: str) -> dict:
    """转人工服务。"""
    return {"success": True, "message": "转人工服务"}


@tool
def search_customer_policy(query: str) -> dict:
    """查询客服知识库。"""
    return {"success": True, "message": "查询客服知识库"}
