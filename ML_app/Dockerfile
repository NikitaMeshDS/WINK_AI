FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY test_in_container.sh .
COPY test.docx .

RUN chmod +x test_in_container.sh

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
