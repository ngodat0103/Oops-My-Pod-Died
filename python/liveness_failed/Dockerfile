FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_TOOL_BIN_DIR=/usr/local/bin
COPY pyproject.toml .
COPY uv.lock .
RUN uv sync
COPY main.py /app/main.py
RUN chown nonroot -R /app && chmod 700 -R /app
USER nonroot
EXPOSE 2509
ENTRYPOINT ["/app/.venv/bin/python3", "main.py"]