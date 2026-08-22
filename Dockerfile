FROM python:3.11-slim

WORKDIR /app

COPY server/requirements.txt ./requiremeog nts.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["python", "server/signaling_server.py", "--port", "8080"]
