#!/bin/bash

# Тест health endpoint
echo "1. Тестирую /health:"
curl -X GET http://localhost:8000/health
echo -e "\n\n"

# Тест analyze endpoint
echo "2. Тестирую /analyze (результат сохраняется в result.json):"
curl -X POST "http://localhost:8000/analyze" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/app/test.docx" \
  -o result.json

echo "Результат сохранен в result.json"
echo "Количество обработанных сцен:"
python3 -c "import json; data = json.load(open('result.json')); print(len(data))"
