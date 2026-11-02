FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.9.5 playwright==1.56.0 && playwright install --with-deps chromium
RUN uv pip install --system --index-url https://download.pytorch.org/whl/cpu torch==2.9.0
COPY server/tool-requirements.lock /tmp/tool-requirements.lock
RUN uv pip install --system --no-deps -r /tmp/tool-requirements.lock
COPY vendor/geo-sleuth /opt/skill
COPY server/skill-uv /usr/local/bin/skill-uv
COPY server/browse.py /opt/skill/scripts/web_page.py
RUN chmod 755 /usr/local/bin/skill-uv && chmod -R a+rX /opt/skill /root/.cache/ms-playwright && mv /root/.cache/ms-playwright /opt/browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers UV=/usr/local/bin/skill-uv GEO_DEVICE=cpu HOME=/cache/home HF_HOME=/cache/huggingface UV_CACHE_DIR=/cache/uv OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
WORKDIR /work
USER 1000:1000
CMD ["python", "/opt/skill/scripts/doctor.py", "--json"]
