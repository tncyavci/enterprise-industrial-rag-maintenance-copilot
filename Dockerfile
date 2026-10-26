FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY app.py mcp_server.py ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[ui,mcp,dev]"

EXPOSE 8090

CMD ["uvicorn", "industrial_rag_copilot.api:app", "--host", "0.0.0.0", "--port", "8090"]
