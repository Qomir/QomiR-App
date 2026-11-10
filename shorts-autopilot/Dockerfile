FROM python:3.11-slim

# FFmpeg (montage + libass pour les sous-titres) et polices des templates.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fontconfig fonts-dejavu-core tzdata \
 && for f in fonts-montserrat fonts-bebas-neue; do \
      apt-get install -y --no-install-recommends "$f" || echo "police $f indisponible, repli DejaVu"; \
    done \
 && fc-cache -f && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY autopilot ./autopilot
COPY config ./config
COPY assets ./assets

# Utilisateur non-root ; data/ et output/ sont des volumes (voir docker-compose.yml)
RUN useradd -m -u 1000 app && mkdir -p /app/data /app/output && chown -R app /app
USER app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "autopilot", "run"]
