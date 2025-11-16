import re
import json
import io
import gc
import torch
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from docx import Document
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ML_FastAPI_App")
# --- End Logging Setup ---

app = FastAPI()
stored_results = None
pipe = None
tokenizer = None

MODEL_NAME = "Qwen/Qwen2.5-14B-Instruct"
BATCH_SIZE = 4
USE_FLASH_ATTENTION = True
MAX_NEW_TOKENS = 800

SYSTEM_PROMPT = """Ты — ассистент режиссёра для извлечения структурированных данных из сценариев.

КРИТИЧЕСКИ ВАЖНО - ТЫ ДОЛЖЕН ВЕРНУТЬ ТОЛЬКО JSON:
- Возвращай ТОЛЬКО валидный JSON объект, БЕЗ ЛЮБЫХ ДОПОЛНИТЕЛЬНЫХ СИМВОЛОВ
- JSON должен начинаться с { и заканчиваться }
- НЕ используй markdown блоки ```json или ```
- НЕ добавляй пояснения, комментарии, объяснения или текст вне JSON
- НЕ добавляй текст до или после JSON
- Если поле пустое — используй "" для строк, [] для массивов
- Все строки в JSON должны быть в двойных кавычках
- Все ключи в JSON должны быть в двойных кавычках
- Строго следуй структуре шаблона
- Проверь, что JSON валидный перед отправкой
"""

USER_PROMPT_TEMPLATE = """
Проанализируй следующую сцену и заполни строго этот JSON-шаблон.
Извлекай ВСЕ данные из текста сцены, включая заголовок.

{{
  "День": "",
  "Серия": "",
  "Сцена": "",
  "Режим": "",
  "Инт / нат": "",
  "Объект": "",
  "Подобъект": "",
  "Синопсис": "",
  "Персонажи": [],
  "Каскадер / Пиротехник": "",
  "Актеры": [],
  "Примечание": "",
  "Массовка": "",
  "Групповка": "",
  "Животное": "",
  "Грим": "",
  "Костюм": "",
  "Реквизит": "",
  "Игровой транспорт": ""
}}

ВАЖНЫЕ ПРАВИЛА ДЛЯ ЗАПОЛНЕНИЯ:

1. ДЕНЬ: Номер дня съемок из текста "ДЕНЬ N" перед сценами
2. СЕРИЯ: Номер серии из текста "N СЕЗОН N СЕРИЯ" или "N СЕРИЯ" в начале документа. Формат: "Серия N"
3. СЦЕНА: Номер сцены из начала заголовка (формат "N."), только число без точки
4. РЕЖИМ: "УТРО", "ДЕНЬ", "ВЕЧЕР", "НОЧЬ", "СУМЕРКИ", "РАССВЕТ"
5. ИНТ / НАТ: Только "ИНТ." или "ЭКСТ." (НАТ = ЭКСТ)
6. ОБЪЕКТ и ПОДОБЪЕКТ: ОБЪЕКТ - основная локация (до первой точки), ПОДОБЪЕКТ - после точки
7. ПЕРСОНАЖИ: Только именованные персонажи (КАПС), формат: ["ИВАН", "МАРИЯ"]
8. АКТЕРЫ: Обычно совпадает с "Персонажи"
9. МАССОВКА: Группы без индивидуализации, формат: "толпа; болельщики"
10. ГРУППОВКА: Организованные группы ("группа студентов", "команда")
11. РЕКВИЗИТ: Только предметы взаимодействия, формат: "телефон; пистолет"
12. ИГРОВОЙ ТРАНСПОРТ: Транспорт, формат: "автомобиль; мотоцикл"
13. ЖИВОТНОЕ: Животные, формат: "собака; кошка"
14. КАСКАДЕР / ПИРОТЕХНИК: Трюки и спецэффекты, формат: "драка; взрыв"
15. ГРИМ: Грим и визуальные эффекты, формат: "кровь; рана"
16. КОСТЮМ: Костюмы и одежда, формат: "форма; маска"
17. СИНОПСИС: Краткое описание действия (1-2 предложения)

ВАЖНО: Не выдумывай данные — только то, что есть в тексте. Если сомневаешься — оставь пустым.

Текст сцены:
{scene_text}
"""

def get_empty_structure() -> Dict:
    return {
        "День": "", "Серия": "", "Сцена": "", "Режим": "", "Инт / нат": "",
        "Объект": "", "Подобъект": "", "Синопсис": "", "Персонажи": [],
        "Каскадер / Пиротехник": "", "Актеры": [], "Примечание": "",
        "Массовка": "", "Групповка": "", "Животное": "", "Грим": "",
        "Костюм": "", "Реквизит": "", "Игровой транспорт": ""
    }

def ensure_full_structure(result: Optional[Dict]) -> Dict:
    if result is None:
        return get_empty_structure()
    empty = get_empty_structure()
    full_result = {**empty, **result}
    for list_field in ["Персонажи", "Актеры"]:
        if not isinstance(full_result.get(list_field), list):
            full_result[list_field] = []
    return full_result

@dataclass
class Scene:
    index: int
    scene_number_raw: Optional[str]
    episode: Optional[str]
    scene_number: Optional[str]
    day: Optional[str]
    heading_raw: str
    location_raw: str
    location_type: Optional[str]
    int_ext: Optional[str]
    time_of_day: Optional[str]
    body_raw: List[str]

def normalize_text_basic(text: str) -> str:
    text = re.sub(r'\r', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[—–]', '-', text)
    return text.strip()

class SceneSegmenter:
    INT_EXT_PATTERN = re.compile(r'\b(?:ИНТ|ЭКСТ|НАТ|ИНТЕРЬЕР|ЭКСТЕРЬЕР|ИНТ\.|ЭКСТ\.|НАТ\.|ИНТ\s|ЭКСТ\s|НАТ\s)\b', re.IGNORECASE)
    TIME_PATTERN = re.compile(r'\b(?:ДЕНЬ|НОЧЬ|УТРО|ВЕЧЕР|СУМЕРКИ|РАССВЕТ|НОЧЬЮ|ДНЕМ|ДНЁМ|ночью|днём)\b', re.IGNORECASE)
    SCENE_NUM_PATTERN = re.compile(r'^(\d+)\.', re.IGNORECASE)
    DAY_PATTERN = re.compile(r'ДЕНЬ\s+(\d+)', re.IGNORECASE)
    EPISODE_PATTERN = re.compile(r'(\d+)\s+СЕЗОН\s+(\d+)\s+СЕРИЯ|(\d+)\s+СЕРИЯ', re.IGNORECASE)
    SCENE_START_PATTERN = re.compile(r'^(\d+)\.\s+', re.IGNORECASE | re.MULTILINE)
    
    def extract_scene_info(self, heading: str) -> Dict:
        info = {"scene_number_raw": None, "episode": None, "scene_number": None, "int_ext": None, "location_raw": "", "time_of_day": None}
        num_match = self.SCENE_NUM_PATTERN.match(heading)
        if num_match:
            scene_num = num_match.group(1)
            info["scene_number"] = scene_num
            info["scene_number_raw"] = scene_num
        int_ext_match = self.INT_EXT_PATTERN.search(heading)
        if int_ext_match:
            int_ext_text = int_ext_match.group(0).upper()
            if "НАТ" in int_ext_text:
                info["int_ext"] = "ЭКСТ."
            elif int_ext_text.startswith("ИНТ"):
                info["int_ext"] = "ИНТ."
            elif int_ext_text.startswith("ЭКСТ"):
                info["int_ext"] = "ЭКСТ."
        time_match = self.TIME_PATTERN.search(heading)
        if time_match:
            info["time_of_day"] = time_match.group(0).strip()
        heading_clean = heading
        if num_match:
            heading_clean = heading_clean.replace(num_match.group(0), "", 1).strip()
        int_ext_pos = -1
        if int_ext_match:
            int_ext_pos = int_ext_match.end()
            while int_ext_pos < len(heading_clean) and heading_clean[int_ext_pos] in ['.', ' ']:
                int_ext_pos += 1
        if int_ext_pos > 0 and int_ext_pos < len(heading_clean):
            location_part = heading_clean[int_ext_pos:].strip()
            if time_match:
                time_text = time_match.group(0).upper()
                time_pos = location_part.upper().find(time_text)
                if time_pos >= 0:
                    location_part = location_part[:time_pos].strip()
            location_part = re.sub(r'\s+\d+\.?\s*$', '', location_part).strip()
            location_part = re.sub(r'[—–\-]+$', '', location_part).strip()
            location_part = re.sub(r'^[—–\-]+', '', location_part).strip()
            if '.' in location_part:
                parts = location_part.split('.', 1)
                object_part = re.sub(r'\s+', ' ', parts[0].strip()).strip()
                subobject_part = re.sub(r'\s+', ' ', parts[1].strip() if len(parts) > 1 else "").strip()
                subobject_part = re.sub(r'\.+$', '', subobject_part).strip()
                info["location_raw"] = object_part
                info["location_type"] = subobject_part if subobject_part else None
            else:
                info["location_raw"] = re.sub(r'\s+', ' ', location_part).strip()
                info["location_type"] = None
        return info
    
    def segment(self, text: str) -> List[Scene]:
        text = normalize_text_basic(text)
        episode_match = self.EPISODE_PATTERN.search(text)
        global_episode = None
        if episode_match:
            if episode_match.group(2):
                global_episode = episode_match.group(2)
            elif episode_match.group(3):
                global_episode = episode_match.group(3)
        matches = list(self.SCENE_START_PATTERN.finditer(text))
        if not matches:
            return []
        scenes = []
        current_day = None
        for i, match in enumerate(matches):
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            scene_text = text[start_pos:end_pos].strip()
            lines = scene_text.split('\n')
            if not lines:
                continue
            if i == 0:
                prev_text = text[:start_pos]
            else:
                prev_end = matches[i - 1].end()
                prev_text = text[prev_end:start_pos]
            day_match = self.DAY_PATTERN.search(prev_text)
            if day_match:
                current_day = day_match.group(1)
            heading = lines[0].strip()
            if len(heading) < 30 and len(lines) > 1:
                next_line = lines[1].strip()
                if next_line and (next_line.isupper() or 'ИНТ' in next_line.upper() or 'ЭКСТ' in next_line.upper() or 'НАТ' in next_line.upper()):
                    heading = heading + " " + next_line
                    body = [line.strip() for line in lines[2:] if line.strip()]
                else:
                    body = [line.strip() for line in lines[1:] if line.strip()]
            else:
                body = [line.strip() for line in lines[1:] if line.strip()]
            scene_info = self.extract_scene_info(heading)
            if global_episode:
                scene_info["episode"] = global_episode
            scene = Scene(index=i, scene_number_raw=scene_info["scene_number_raw"], episode=scene_info.get("episode"),
                         scene_number=scene_info.get("scene_number"), day=current_day, heading_raw=heading,
                         location_raw=scene_info["location_raw"], location_type=scene_info.get("location_type"),
                         int_ext=scene_info["int_ext"], time_of_day=scene_info["time_of_day"], body_raw=body)
            scenes.append(scene)
        return scenes

def extract_json_from_output(output_text: str) -> Optional[Dict]:
    if not output_text:
        return None
    match = re.search(r"\{.*\}", output_text, re.DOTALL)
    if not match:
        return None
    json_str = match.group(0).strip()
    json_str = json_str.replace("'}", "}")
    json_str = json_str.replace("{'", "{")
    json_str = json_str.replace("':", ":")
    json_str = json_str.replace(", '", ", ")
    json_str = json_str.replace("['", "[")
    json_str = json_str.replace("']", "]")
    json_str = re.sub(r",\s*([\}\]])", r"\1", json_str)
    json_str = re.sub(r":\s*([^\",\[\]\{\}]+?)([,\}\]])", r': "\1"\2', json_str)
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    if open_braces > close_braces:
        json_str += '}' * (open_braces - close_braces)
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    if open_brackets > close_brackets:
        json_str += ']' * (open_brackets - close_brackets)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        for i in range(len(json_str), 0, -1):
            test_json = json_str[:i]
            if test_json.count('{') == test_json.count('}'):
                try:
                    return json.loads(test_json)
                except:
                    continue
        return None

def extract_with_rules(scene: Scene, scene_text: str, episode: str = "") -> Dict:
    episode_value = scene.episode if scene.episode else episode
    scene_number_value = scene.scene_number if scene.scene_number else (scene.scene_number_raw if scene.scene_number_raw else "")
    return {
        "День": scene.day or "",
        "Серия": f"Серия {episode_value}" if episode_value else episode,
        "Сцена": scene_number_value,
    }

def extract_with_model(scene: Scene, scene_text: str, episode: str) -> Optional[Dict]:
    full_scene_text = f"Заголовок: {scene.heading_raw}\n\nТекст сцены:\n{scene_text}"
    context_parts = []
    if scene.day:
        context_parts.append(f"Контекст: ДЕНЬ {scene.day}")
    if episode:
        context_parts.append(f"Контекст: {episode}")
    if context_parts:
        full_scene_text = "\n".join(context_parts) + "\n\n" + full_scene_text
    prompt = USER_PROMPT_TEMPLATE + f"\n\nТекст сцены:\n{full_scene_text}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    try:
        try:
            output = pipe(messages, return_full_text=False, response_format={"type": "json_object"})
        except:
            output = pipe(messages, return_full_text=False)
        if isinstance(output, list) and len(output) > 0:
            text = output[0].get("generated_text", "") if isinstance(output[0], dict) else str(output[0])
        elif isinstance(output, dict):
            text = output.get("generated_text", "")
        else:
            text = str(output)
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return extract_json_from_output(text)
    except Exception as e:
        logger.error(f"Error during model extraction for scene {scene.index}: {e}", exc_info=True)
        return None

def extract_with_model_batch(scenes_data: List[Tuple[Scene, str, str]]) -> List[Optional[Dict]]:
    messages_batch = []
    for scene, scene_text, episode in scenes_data:
        full_scene_text = f"Заголовок: {scene.heading_raw}\n\nТекст сцены:\n{scene_text}"
        context_parts = []
        if scene.day:
            context_parts.append(f"Контекст: ДЕНЬ {scene.day}")
        if episode:
            context_parts.append(f"Контекст: {episode}")
        if context_parts:
            full_scene_text = "\n".join(context_parts) + "\n\n" + full_scene_text
        prompt = USER_PROMPT_TEMPLATE + f"\n\nТекст сцены:\n{full_scene_text}"
        messages_batch.append([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}])
    try:
        try:
            outputs = pipe(messages_batch, return_full_text=False, batch_size=len(messages_batch), response_format={"type": "json_object"})
        except:
            outputs = pipe(messages_batch, return_full_text=False, batch_size=len(messages_batch))
        results = []
        for output in outputs:
            if isinstance(output, list) and len(output) > 0:
                text = output[0].get("generated_text", "") if isinstance(output[0], dict) else str(output[0])
            elif isinstance(output, dict):
                text = output.get("generated_text", "")
            else:
                text = str(output)
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:].strip()
            elif text.startswith("```"):
                text = text[3:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
            results.append(extract_json_from_output(text))
        torch.cuda.empty_cache()
        gc.collect()
        return results
    except Exception as e:
        logger.error(f"Error during batch model extraction: {e}", exc_info=True)
        torch.cuda.empty_cache()
        gc.collect()
        return [None] * len(scenes_data)

def cascade_extract(scene: Scene, scene_text: str, episode: str, use_model: bool = True) -> Dict:
    rules_result = extract_with_rules(scene, scene_text, episode)
    model_result = extract_with_model(scene, scene_text, episode) if use_model else None
    model_result = ensure_full_structure(model_result)
    final_result = {**model_result, **rules_result}
    final_result["_SceneIndex"] = scene.index
    final_result["_HeadingRaw"] = scene.heading_raw
    return final_result

def process_text(text: str, episode: str) -> List[Dict]:
    logger.info("Segmenting text into scenes...")
    segmenter = SceneSegmenter()
    scenes = segmenter.segment(text)
    if not scenes:
        logger.warning("No scenes found in the provided text.")
        return []
    
    logger.info(f"Found {len(scenes)} scenes. Starting extraction.")
    results = []
    if BATCH_SIZE > 1 and len(scenes) > 1 and tokenizer is not None:
        scenes_data = [(scene, scene.heading_raw + "\n" + "\n".join(scene.body_raw), episode) for scene in scenes]
        for i in range(0, len(scenes_data), BATCH_SIZE):
            batch = scenes_data[i:i+BATCH_SIZE]
            logger.info(f"Processing batch {i//BATCH_SIZE + 1}/{(len(scenes_data) + BATCH_SIZE - 1) // BATCH_SIZE} with {len(batch)} scenes.")
            try:
                batch_results = extract_with_model_batch(batch)
                for j, (scene, _, _) in enumerate(batch):
                    logger.info(f"Extracting data for scene {scene.index + 1}...")
                    model_result = batch_results[j]
                    rules_result = extract_with_rules(scene, "", episode)
                    model_result = ensure_full_structure(model_result)
                    result = {**model_result, **rules_result}
                    result["_SceneIndex"] = scene.index
                    result["_HeadingRaw"] = scene.heading_raw
                    results.append(result)
            except Exception as e:
                logger.error(f"Error processing batch, falling back to individual processing for this batch. Error: {e}", exc_info=True)
                for scene, scene_text_full, _ in batch:
                    logger.info(f"Processing scene {scene.index + 1} individually due to batch error.")
                    try:
                        result = cascade_extract(scene, scene_text_full, episode, use_model=True)
                        results.append(result)
                    except Exception as e_single:
                        logger.error(f"Error processing single scene {scene.index}: {e_single}. Using rules-based extraction only.", exc_info=True)
                        rules_result = extract_with_rules(scene, scene_text_full, episode)
                        result = ensure_full_structure(None)
                        result.update(rules_result)
                        result["_SceneIndex"] = scene.index
                        result["_HeadingRaw"] = scene.heading_raw
                        results.append(result)
    else:
        for i, scene in enumerate(scenes):
            logger.info(f"Processing scene {i+1}/{len(scenes)} (Scene Number: {scene.scene_number_raw}) individually.")
            scene_text = scene.heading_raw + "\n" + "\n".join(scene.body_raw)
            try:
                result = cascade_extract(scene, scene_text, episode, use_model=True)
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing single scene {scene.index}: {e}. Using rules-based extraction only.", exc_info=True)
                rules_result = extract_with_rules(scene, scene_text, episode)
                result = ensure_full_structure(None)
                result.update(rules_result)
                result["_SceneIndex"] = scene.index
                result["_HeadingRaw"] = scene.heading_raw
                results.append(result)
    logger.info(f"Finished text processing. Extracted data for {len(results)} scenes.")
    return results

logger.info("Загрузка модели...")
device = "cuda:0" if torch.cuda.is_available() else "cpu"
model_kwargs = {"torch_dtype": torch.float16, "device_map": device, "trust_remote_code": True}
if USE_FLASH_ATTENTION and torch.cuda.is_available():
    try:
        import flash_attn
        model_kwargs["attn_implementation"] = "flash_attention_2"
        logger.info("Flash Attention 2 enabled.")
    except ImportError:
        logger.warning("Flash Attention 2 is not available, using default attention.")
        pass
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, **model_kwargs)
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, max_new_tokens=MAX_NEW_TOKENS,
                temperature=0.1, do_sample=True, pad_token_id=tokenizer.eos_token_id)
torch.cuda.empty_cache()
gc.collect()
logger.info("Модель загружена!")

def read_docx_text(file_content: bytes) -> str:
    doc = Document(io.BytesIO(file_content))
    return "\n".join(p.text for p in doc.paragraphs)

@app.post("/analyze")
async def analyze_script(file: UploadFile = File(...)):
    global stored_results
    logger.info(f"--- Received new analysis request for file: {file.filename} ---")
    if not file.filename.endswith('.docx'):
        logger.error(f"Invalid file type received: {file.filename}")
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .docx")
    if not pipe:
        logger.error("Analysis request received but model is not loaded.")
        raise HTTPException(status_code=500, detail="Модель не загружена")
    try:
        file_content = await file.read()
        text = read_docx_text(file_content)
        if not text or len(text.strip()) == 0:
            logger.error("File is empty or text could not be read.")
            raise HTTPException(status_code=400, detail="Файл пуст или не удалось прочитать текст")
        
        logger.info("Starting text processing...")
        episode_match = re.search(r'(\d+)\s+СЕЗОН\s+(\d+)\s+СЕРИЯ|(\d+)\s+СЕРИЯ', text, re.IGNORECASE)
        if episode_match:
            episode = f"Серия {episode_match.group(3) if episode_match.group(3) else episode_match.group(2)}"
        else:
            episode = ""
        
        results = process_text(text, episode)
        stored_results = results
        logger.info(f"Processing for {file.filename} complete. Returning {len(results)} scenes.")
        return JSONResponse(content=results)
    except HTTPException as http_exc:
        logger.error(f"HTTP exception during analysis for {file.filename}: {http_exc.detail}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during analysis for {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

@app.get("/result")
async def get_result():
    global stored_results
    if stored_results is None:
        raise HTTPException(status_code=404, detail="Результаты не найдены. Сначала загрузите файл через /analyze")
    return JSONResponse(content=stored_results)

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
