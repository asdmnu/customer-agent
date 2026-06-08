"""请求路由服务。"""

from pydantic import BaseModel, Field

from backend.core.config import load_classifier_prompt
from backend.models.factory import get_chat_model


class RouteDecision(BaseModel):
    """分类结果结构。"""

    route: str = Field(..., description="qa 或 action")
    reason: str = Field(..., description="简短路由原因")


VALID_ROUTES = {"qa", "action"}


ACTION_HINTS = (
    "开通",
    "取消",
    "办理",
    "申请",
    "帮我",
    "修改",
    "重置",
    "激活",
)


def _build_default_route_decision(
    reason: str = "分类模型未返回有效结果，默认按问答处理。",
) -> RouteDecision:
    """构造默认的大类路由结果。"""
    return RouteDecision(route="qa", reason=reason)


def _classify_query_with_model(query: str, extra_context: str = "") -> RouteDecision:
    """使用模型补充判断 qa / action 路由。"""
    prompt = load_classifier_prompt().format(
        query=query,
        extra_context=extra_context or "None",
    )
    model = get_chat_model().with_structured_output(RouteDecision)
    result = model.invoke(prompt)

    if result is None:
        return _build_default_route_decision()
    if isinstance(result, RouteDecision):
        if result.route in VALID_ROUTES:
            return result
        return _build_default_route_decision(reason=f"分类模型返回了无效路由：{result.route}")
    if isinstance(result, dict):
        route = str(result.get("route", "")).strip().lower()
        reason = str(result.get("reason", "")).strip()
        if route in VALID_ROUTES:
            return RouteDecision(route=route, reason=reason or "分类模型返回字典结果。")

    return _build_default_route_decision(reason="分类模型返回了无法解析的结果。")


def route_query(query: str, extra_context: str = "", history_text: str = "") -> RouteDecision:
    """优先使用规则快速判断，并保留分类链作为补充。"""
    lowered = query.strip().lower()
    if any(keyword in query for keyword in ACTION_HINTS):
        return RouteDecision(route="action", reason="命中执行类关键词")
    if lowered.startswith("为什么") or lowered.startswith("怎么办"):
        return RouteDecision(route="qa", reason="命中问答类前缀")
    merged_context = extra_context.strip()
    if history_text.strip():
        merged_context = f"{merged_context}\n\n历史对话：\n{history_text}".strip()
    return _classify_query_with_model(query=query, extra_context=merged_context)
