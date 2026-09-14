FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY tests ./tests
COPY pytest.ini .

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "booking_api.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
