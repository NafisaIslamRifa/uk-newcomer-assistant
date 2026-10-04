# One image for every UKNest service. docker-compose runs it three ways:
#   init -> python -m scripts.bootstrap      (build the index once)
#   mcp  -> python -m mcp_server.server      (tools over HTTP)
#   app  -> streamlit run app/streamlit_app.py (the web UI, default command)

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTEMBED_CACHE_PATH=/models

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model into the image, so containers start fast
# and never download it at runtime
RUN python -c "from fastembed import TextEmbedding; \
TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"

COPY . .

# Run as a normal user, not root
RUN useradd --create-home --uid 1000 uknest && chown -R uknest:uknest /app /models
USER uknest

EXPOSE 8501 8000

CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
