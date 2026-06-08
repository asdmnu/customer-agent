# 客服助手 3

客服助手 3 是一个客服场景的演示项目，拆分为两条主要流程：
- `qa`：分类 -> 检索 -> 回答
- `action`：分类 -> LangChain 智能体 -> 业务工具

这个仓库整体结构与 `客服agent2` 类似，但将 LangGraph 工作流替换成了更轻量的服务编排层。

## 项目结构

```text
.
|- backend/              应用、流程、路由、工具、记忆、存储
|- frontend/             Streamlit 演示页面
|- data/                 示例知识库文件
|- logs/                 运行日志
|- Dockerfile            Docker 镜像构建文件
|- docker-compose.yml    Docker Compose 配置文件
|- requirements.txt
|- .env.example
```

## 主流程

1. FastAPI 接收用户问题。
2. 路由层判断请求应进入 `qa` 还是 `action`。
3. `qa` 路径：
   - 检索知识库上下文
   - 基于检索结果生成回答
4. `action` 路径：
   - 运行受约束的 `create_agent(...)`
   - 让智能体调用确定性的客服工具
   - 返回最终执行结果

## 本地运行

1. 将 `.env.example` 复制为 `.env`
2. 填写 `DASHSCOPE_API_KEY`
3. 启动 API：

```bash
uvicorn backend.app.api_server:app --reload
```

4. 如需体验前端演示页，可额外启动 Streamlit：

```bash
streamlit run frontend/app.py
```

## Docker 运行

1. 准备好 `.env`
2. 启动全部服务：

```bash
docker compose up --build
```

启动完成后：
- API：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:8501`

首次启动时，如果 pgvector 数据表仍为空，`api` 服务会自动初始化知识库。
