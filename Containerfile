FROM quay.io/hummingbird/python:latest-fips-builder AS builder
USER 0
WORKDIR /app
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

FROM quay.io/hummingbird/python:latest-fips
LABEL name="mcp-pcloud-crunchtools" \
      version="2.1.0" \
      summary="Secure MCP server for pCloud cloud storage" \
      maintainer="crunchtools.com" \
      org.opencontainers.image.source="https://github.com/crunchtools/mcp-pcloud" \
      org.opencontainers.image.description="Secure MCP server for pCloud cloud storage" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
COPY --from=builder /app/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
EXPOSE 8028
ENTRYPOINT ["python", "-m", "mcp_pcloud_crunchtools"]
