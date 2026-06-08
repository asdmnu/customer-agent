"""执行类请求子路由服务。"""

from pydantic import BaseModel, Field

from backend.core.config import load_action_category_classifier_prompt
from backend.models.factory import get_chat_model


class ActionRouteDecision(BaseModel):
    """执行类子场景分类结果。"""

    category: str = Field(..., description="roaming、plan_change、billing、sim_service 之一")
    reason: str = Field(..., description="简短分类原因")


VALID_ACTION_CATEGORIES = {"roaming", "plan_change", "billing", "sim_service"}


ROAMING_HINTS = ("漫游", "出国", "国际流量", "漫游包")
PLAN_HINTS = ("套餐", "升档", "降档", "迁转", "改套餐")
BILLING_HINTS = ("账单", "欠费", "扣费", "缴费", "费用")
SIM_HINTS = ("挂失", "补卡", "复机", "停机", "sim", "卡丢了")


def _build_default_action_route_decision(
    reason: str = "子分类模型未返回有效结果，默认按 billing 处理。",
) -> ActionRouteDecision:
    """构造默认的执行类子场景路由结果。"""
    return ActionRouteDecision(category="billing", reason=reason)


def _classify_action_query_with_model(query: str, extra_context: str = "") -> ActionRouteDecision:
    """使用模型补充判断执行类子场景。"""
    prompt = load_action_category_classifier_prompt().format(
        query=query,
        extra_context=extra_context or "无",
    )
    model = get_chat_model().with_structured_output(ActionRouteDecision)
    result = model.invoke(prompt)

    if result is None:
        return _build_default_action_route_decision()
    if isinstance(result, ActionRouteDecision):
        if result.category in VALID_ACTION_CATEGORIES:
            return result
        return _build_default_action_route_decision(reason=f"子分类模型返回了无效类别：{result.category}")
    if isinstance(result, dict):
        category = str(result.get("category", "")).strip().lower()
        reason = str(result.get("reason", "")).strip()
        if category in VALID_ACTION_CATEGORIES:
            return ActionRouteDecision(category=category, reason=reason or "子分类模型返回字典结果。")

    return _build_default_action_route_decision(reason="子分类模型返回了无法解析的结果。")


def route_action_query(query: str, extra_context: str = "", history_text: str = "") -> ActionRouteDecision:
    """优先用规则做子场景判断，不明确时再交给模型。"""
    normalized_query = query.strip().lower()

    if any(keyword in query for keyword in ROAMING_HINTS):
        return ActionRouteDecision(category="roaming", reason="命中漫游类关键词")
    if any(keyword in query for keyword in PLAN_HINTS):
        return ActionRouteDecision(category="plan_change", reason="命中套餐类关键词")
    if any(keyword in query for keyword in BILLING_HINTS):
        return ActionRouteDecision(category="billing", reason="命中账单类关键词")
    if any(keyword in normalized_query for keyword in SIM_HINTS) or any(keyword in query for keyword in SIM_HINTS):
        return ActionRouteDecision(category="sim_service", reason="命中挂失补卡复机类关键词")

    merged_context = extra_context.strip()
    if history_text.strip():
        merged_context = f"{merged_context}\n\n历史对话：\n{history_text}".strip()
    return _classify_action_query_with_model(query=query, extra_context=merged_context)
