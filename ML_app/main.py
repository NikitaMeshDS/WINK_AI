import re
import json
import os
from docx import Document
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import httpx
import uvicorn

# ДОБАВЛЕН ИМПОРТ ДЛЯ РАБОТЫ С SOCKS-ПРОКСИ
from httpx_socks import AsyncProxyTransport

app = FastAPI()

SYSTEM_PROMPT = """Ты — ассистент режиссёра.
Возвращай ТОЛЬКО JSON, начинающийся с { и заканчивающийся }.
Никаких пояснений, комментариев, ```json и текста вне JSON.
Если нет данных — пиши "".
"""

USER_PROMPT_TEMPLATE = """
Проанализируй следующую сцену и заполни строго этот JSON-шаблон:

{{
  "Серия": "{episode}",
  "НомерСцены": "",
  "Режим": "",
  "Объект": "",
  "Подобъект": "",
  "Синопсис": "",
  "Персонажи": [],
  "Массовка/Группировка": "",
  "Грим/Костюм": "",
  "Реквизит/Игровой транспорт/Животное": "",
  "Декорация": "",
  "Каскадёр/Трюк": "",
  "Администрация/Спецэффект": "",
  "Операторская техника": "",
  "Лед экраны": ""
}}

Текст сцены:
{scene_text}
"""

API_KEY = os.getenv("GROQ_API_KEY", "")
API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

def read_docx_text(file_content: bytes) -> str:
    import io
    doc = Document(io.BytesIO(file_content))
    return "\n".join(p.text for p in doc.paragraphs)

def normalize_text(text: str) -> str:
    text = re.sub(r'\r', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def split_scenes(text: str):
    text = normalize_text(text)
    pattern = re.compile(
        r'(?=(?:^|\n)\s*'
        r'(?:СЦЕНА\s*\d+[А-ЯA-Z\-–\.]*\.?|[0-9]+[\-–\.][0-9А-ЯA-Z\-–]*\.?)\s*'
        r'(?:ИНТ|ЭКСТ|НАТ|ИНТЕРЬЕР|ЭКСТЕРЬЕР|ИНТ\.|ЭКСТ\.|НАТ\.)'
        r'.{0,120}?'
        r'(?:\s+(?:ДЕНЬ|НОЧЬ|УТРО|ВЕЧЕР|СУМЕРКИ|НОЧЬЮ|ДНЕМ|ДНЁМ))?'
        r'(?:\n|$))',
        flags=re.IGNORECASE
    )
    parts = re.split(pattern, text)
    scenes = [p.strip() for p in parts if p.strip()][1:]
    return scenes

def extract_json_from_output(output_text):
    match = re.search(r"\{.*\}", output_text, re.DOTALL)
    if not match:
        return None
    json_str = match.group(0).strip().replace("'}", "}").replace("`", "")
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None

async def extract_from_scene(scene_text, episode):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY не установлен")

    prompt = USER_PROMPT_TEMPLATE.format(scene_text=scene_text, episode=episode)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    
    # ИСПОЛЬЗУЕМ СПЕЦИАЛЬНОЕ DNS ИМЯ ДЛЯ ДОСТУПА К ХОСТУ ИЗНУТРИ DOCKER
    proxy_url = "socks5://host.docker.internal:1080"
    
    transport = AsyncProxyTransport.from_url(proxy_url)

    async with httpx.AsyncClient(transport=transport, timeout=120.0) as client:
        try:
            response = await client.post(
                API_URL,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "max_tokens": 512, "temperature": 0.0}
            )
            response.raise_for_status()
            result = response.json()
            text = result["choices"][0]["message"]["content"]
            return extract_json_from_output(text)
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Groq API error: {e.response.text}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Ошибка подключения к API через прокси (host.docker.internal): {e}")

async def process_text(text, episode):
    scenes = split_scenes(text)
    results = []
    for scene in scenes:
        data = await extract_from_scene(scene, episode)
        if data:
            results.append(data)
    return results

@app.post("/analyze")
async def analyze_script(file: UploadFile = File(...)):
    if not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .docx")
    
    try:
        file_content = await file.read()
        text = read_docx_text(file_content)
        
        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Файл пуст или не удалось прочитать текст")
        
        episode_match = re.search(r"(ПЕРВАЯ|ВТОРАЯ|ТРЕТЬЯ)\s+СЕРИЯ", text, re.IGNORECASE)
        episode = episode_match.group(1).capitalize() + " серия" if episode_match else "1"
        
        results = await process_text(text, episode)
        return JSONResponse(content=results)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)