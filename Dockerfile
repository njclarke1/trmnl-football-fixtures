FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY tests/fixtures/ tests/fixtures/
ENV PYTHONUNBUFFERED=1 TZ=Europe/London
EXPOSE 3458
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:3458", "app.main:app"]
