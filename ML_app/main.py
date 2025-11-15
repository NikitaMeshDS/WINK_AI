import re
import json
import os
import io
import logging
from docx import Document
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from transformers import pipeline

# --- Logging Setup ---
# Using standard logging library to output information to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ML_app")
# --- End Logging Setup ---

app = FastAPI()

# Глобальная переменная для хранения результатов
stored_results = None

# Инициализация pipeline при старте приложения
logger.info("Загрузка модели...")
pipe = pipeline(
    "text-generation", 
    model="mistralai/Mistral-7B-Instruct-v0.2", 
    device_map="auto",
    model_kwargs={"pad_token_id": 2}
)
logger.info("Модель загружена!")

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

def read_docx_text(file_content: bytes) -> str:
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
                r'(?:СЦЕНА\s*\d+[А-ЯA-Z\-–\.]*\.?|[0-9]+[\-–\.][0-9А-ЯA-Z\-–]*\.?)'
        r'\s*'
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
        logger.warning("Could not find JSON in the model output.")
        return None

    json_str = match.group(0)
    json_str = json_str.strip()
    json_str = json_str.replace("'}", "}")
    json_str = re.sub(r",\s*}", "}", json_str)
    json_str = re.sub(r",\s*]", "]", json_str)

    try:
        # Log the extracted JSON for verification
        parsed_json = json.loads(json_str)
        logger.info(f"Successfully extracted JSON: {json.dumps(parsed_json, ensure_ascii=False, indent=2)}")
        return parsed_json
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from model output. Error: {e}. String was: {json_str}")
        return None

def extract_from_scene(scene_text, episode):
    if not pipe:
        raise HTTPException(status_code=500, detail="Модель не загружена")
    
    prompt = USER_PROMPT_TEMPLATE.format(scene_text=scene_text, episode=episode)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]

    try:
        output = pipe(messages, max_new_tokens=512, do_sample=False)
        
        # Универсальная обработка вывода
        if isinstance(output, list):
            result = output[0].get("generated_text", output[0])
        else:
            result = output
        
        # Если результат — список сообщений (chat-формат)
        if isinstance(result, list):
            assistant_message = next(
                (m.get("content", "") for m in result if m.get("role") == "assistant"), 
                ""
            )
            text = assistant_message
        elif isinstance(result, dict):
            text = result.get("generated_text", "")
        else:
            text = str(result)
        
        return extract_json_from_output(text)
    except Exception as e:
        logger.error(f"Exception during model inference: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка модели: {str(e)}")

def process_text(text, episode):
    scenes = split_scenes(text)
    results = []
    logger.info(f"Found {len(scenes)} scenes to process.")
    for i, scene in enumerate(scenes, start=1):
        logger.info(f"--- Processing scene {i}/{len(scenes)} ---")
        data = extract_from_scene(scene, episode)
        if data:
            results.append(data)
    logger.info(f"Finished processing text. Extracted data for {len(results)} scenes.")
    return results

@app.post("/analyze")
async def analyze_script(file: UploadFile = File(...)):
    global stored_results
    
    logger.info(f"Received request to analyze file: {file.filename}")

    if not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .docx")
    
    if not pipe:
        raise HTTPException(status_code=500, detail="Модель не загружена")
    
    try:
        file_content = await file.read()
        text = read_docx_text(file_content)
        logger.info(f"--- Full text from DOCX ---\n{text}\n--- End of text ---")
        logger.info(f"--- Full text from DOCX ---\n{text}\n--- End of text ---")

        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Файл пуст или не удалось прочитать текст")

        episode_match = re.search(r"(ПЕРВАЯ|ВТОРАЯ|ТРЕТЬЯ)\s+СЕРИЯ", text, re.IGNORECASE)
        episode = episode_match.group(1).capitalize() + " серия" if episode_match else "1"
        logger.info(f"Determined episode: {episode}")

        results = process_text(text, episode)

        # Сохраняем результаты для доступа через /result
        stored_results = results
        logger.info(f"Analysis complete. Processed {len(results)} scenes successfully.")

        # удалить нижнию строку
        return JSONResponse(content={"status": "success", "scenes_processed": len(results)})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

@app.get("/result")
async def get_result():
    """Получить результаты последней обработки"""
    global stored_results
    
    if stored_results is None:
        raise HTTPException(status_code=404, detail="Результаты не найдены. Сначала загрузите файл через /analyze")
    
    return JSONResponse(content=stored_results)

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
