FROM quay.io/hummingbird/python:3.14-fips-builder AS lock
USER 0
RUN pip install --no-cache-dir uv==0.13.7
WORKDIR /lock
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project \
      --format requirements-txt -o /requirements.txt

FROM quay.io/hummingbird/python:3.14-fips-builder AS builder
USER 0
WORKDIR /app
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
COPY --from=lock /requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-deps -r /tmp/requirements.txt
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

FROM quay.io/hummingbird/python:3.14-fips
LABEL name="mcp-pcloud-crunchtools" \
      version="3.3.1" \
      summary="Secure MCP server for pCloud cloud storage" \
      maintainer="crunchtools.com" \
      org.opencontainers.image.source="https://github.com/crunchtools/mcp-pcloud" \
      org.opencontainers.image.description="Secure MCP server for pCloud cloud storage" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
COPY --from=builder /app/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
EXPOSE 8028
ENTRYPOINT ["python", "-m", "mcp_pcloud_crunchtools"]
