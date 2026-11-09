FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home scanner && chown -R scanner:scanner /app
USER scanner
# A default container invocation must not fetch, score remotely, upload or send mail.
CMD ["python", "-B", "tools/capture_and_score.py", "--help"]
