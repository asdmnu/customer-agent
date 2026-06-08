from langchain_core.tools import tool


@tool
def report_sim_loss(phone_number: str) -> dict:
    """办理挂失。"""
    return {"success": True, "message": "办理挂失"}


@tool
def restore_service(phone_number: str) -> dict:
    """办理复机。"""
    return {"success": True, "message": "办理复机"}


@tool
def request_sim_replacement(phone_number: str) -> dict:
    """办理补卡。"""
    return {"success": True, "message": "办理补卡"}
