FROM python:3.11-slim

# HF Spaces requiere usuario no-root con UID 1000
RUN useradd -m -u 1000 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

# Carpeta de datos persistente
RUN mkdir -p /data && chown appuser:appuser /data

USER appuser

ENV PORT=7860
ENV DB_PATH=/data/centinela_vial.db

EXPOSE 7860

CMD ["python", "main.py"]
