import re
import json
import io
import sys
import gc
import torch
import logging
import asyncio
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

import flash_attn
from docx import Document
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import uvicorn
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ML_app")

app = FastAPI()
stored_results = None
pipe = None
tokenizer = None

MODEL_NAME = "Qwen/Qwen2.5-14B-Instruct"
BATCH_SIZE = 8
USE_FLASH_ATTENTION = True
MAX_NEW_TOKENS = 1500

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

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА ЗАПОЛНЕНИЯ ПОЛЕЙ:

1. ДЕНЬ: Извлекай номер дня съемок из текста "ДЕНЬ N", который может находиться перед группой сцен. Если в тексте сцены нет указания дня, оставь поле пустым.

2. СЕРИЯ: Определяй номер серии из текста "N СЕЗОН N СЕРИЯ" или "N СЕРИЯ" в начале документа. Обязательный формат вывода: "Серия N" (например: "Серия 1"). Если номер серии не указан, оставь пустым.

3. СЦЕНА: Извлекай ТОЛЬКО числовой номер сцены из начала заголовка сцены. 
   - Если формат "N-M" или "N-M-А" (например: "1-2" или "1-2-А"), извлекай ТОЛЬКО часть после дефиса (т.е. "2" или "2-А").
   - Если формат "N." (например: "1."), извлекай ТОЛЬКО число без точки (т.е. "1").
   - ЗАПРЕЩЕНО включать описание локации или другие слова.
   - ЗАПРЕЩЕНО добавлять слово "Сцена" перед числом.
   Примеры: "1. УТРО. ЛЕС" → "1"; "1-2. НАТ. ГОРЫ" → "2"; "1-2-А. ИНТ. ДОМ" → "2-А"

4. РЕЖИМ: Определяй время суток. Допустимые значения ТОЛЬКО: "УТРО", "ДЕНЬ", "ВЕЧЕР", "НОЧЬ", "СУМЕРКИ", "РАССВЕТ".
   - КРИТИЧЕСКИ ВАЖНО: "НАТ" (натура) - это НЕ режим, это тип локации (интерьер/экстерьер).
   - Если режим не указан явно, оставь поле пустым.

5. ИНТ / НАТ: Определяй тип локации. Допустимые значения ТОЛЬКО: "ИНТ." или "ЭКСТ.".
   - "НАТ" (натура) эквивалентно "ЭКСТ." (экстерьер).
   - ЗАПРЕЩЕНО включать описание локации или другие слова.
   - Если тип локации не указан, оставь поле пустым.

6. ОБЪЕКТ и ПОДОБЪЕКТ: Извлекай локацию из заголовка сцены.
   - ОБЪЕКТ: основная локация (часть до первой точки в заголовке, после номера сцены и типа локации).
   - ПОДОБЪЕКТ: уточняющая локация (часть после первой точки).
   - Пример: заголовок "1. НАТ. ЛЕС.ПОЛЯНА" → Объект: "ЛЕС", Подобъект: "ПОЛЯНА"
   - Если локация не разделена точкой, заполняй только ОБЪЕКТ, ПОДОБЪЕКТ оставляй пустым.

7. ПЕРСОНАЖИ: Извлекай имена именованных персонажей, которые упоминаются в сцене.
   - Формат: массив строк в ВЕРХНЕМ РЕГИСТРЕ, например: ["ИВАН", "МАРИЯ", "ПЕТР"]
   - ЗАПРЕЩЕНО использовать объекты с полями "Имя", "Роль", "Name" и т.д.
   - Только простой массив строк с именами.
   - Если именованных персонажей нет, верни пустой массив [].

8. АКТЕРЫ: Список актеров, исполняющих роли персонажей в сцене.
   - Формат: массив строк, обычно совпадает с полем "Персонажи".
   - ЗАПРЕЩЕНО использовать строку "" - всегда возвращай массив (даже пустой []).
   - Если актеры не указаны, но есть персонажи, используй те же имена, что в "Персонажи".

9. МАССОВКА: Группы людей без индивидуализации (толпа, зрители, прохожие и т.д.).
   - Формат: строка с перечислением групп через точку с запятой.
   - ОБЯЗАТЕЛЬНО указывай количество людей в скобках для каждой группы.
   - Пример: "толпа (50); болельщики (30); прохожие (15)"
   - Если массовки нет, оставь пустым.

10. ГРУППОВКА: Организованные группы людей с определенной функцией (группа студентов, команда, отряд и т.д.).
    - Формат: строка с описанием группы, например: "группа студентов", "команда футболистов"
    - Если группировки нет, оставь пустым.

11. РЕКВИЗИТ: Предметы, с которыми взаимодействуют персонажи в сцене.
    - Формат: строка с перечислением предметов через точку с запятой, например: "телефон; пистолет; документы"
    - Указывай только предметы, которые активно используются в сцене.
    - Если реквизита нет, оставь пустым.

12. ИГРОВОЙ ТРАНСПОРТ: Транспортные средства, используемые в сцене.
    - Формат: строка с перечислением через точку с запятой, например: "автомобиль; мотоцикл; автобус"
    - Если транспорта нет, оставь пустым.

13. ЖИВОТНОЕ: Животные, присутствующие в сцене.
    - Формат: строка с перечислением через точку с запятой, например: "собака; кошка; лошадь"
    - Если животных нет, оставь пустым.

14. КАСКАДЕР / ПИРОТЕХНИК: Трюки, спецэффекты и опасные сцены, требующие участия каскадеров или пиротехников.
    - Формат: строка с описанием, например: "драка; взрыв; падение с высоты"
    - Если трюков нет, оставь пустым.

15. ГРИМ: Требования к гриму и визуальным эффектам (кровь, раны, старение, фантастические элементы и т.д.).
    - Формат: строка с описанием, например: "кровь; рана на лице; старение"
    - Если грима нет, оставь пустым.

16. КОСТЮМ: Требования к костюмам и одежде персонажей.
    - Формат: строка с описанием, например: "военная форма; маска; вечернее платье"
    - Если особых требований к костюмам нет, оставь пустым.

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

def normalize_characters(characters):
    if not characters:
        return []
    normalized = []
    for char in characters:
        if isinstance(char, dict):
            name = char.get("Имя") or char.get("имя") or char.get("Name") or char.get("name") or ""
            if name:
                normalized.append(str(name).upper().strip())
        elif isinstance(char, str):
            normalized.append(char.upper().strip())
    return normalized

def normalize_mode(mode: str) -> str:
    if not mode:
        return ""
    mode_upper = mode.upper().strip()
    if "НАТ" in mode_upper:
        return ""
    valid_modes = ["УТРО", "ДЕНЬ", "ВЕЧЕР", "НОЧЬ", "СУМЕРКИ", "РАССВЕТ"]
    if mode_upper in valid_modes:
        return mode_upper
    return ""

def normalize_int_ext(int_ext: str) -> str:
    if not int_ext:
        return ""
    int_ext_upper = int_ext.upper().strip()
    if "НАТ" in int_ext_upper or "ЭКСТ" in int_ext_upper:
        return "ЭКСТ."
    elif "ИНТ" in int_ext_upper:
        return "ИНТ."
    return ""

def normalize_scene_number(scene: str) -> str:
    if not scene:
        return ""
    scene = scene.strip()
    scene = re.sub(r'^Сцена\s+', '', scene, flags=re.IGNORECASE)
    scene = re.sub(r'\.\s*.*$', '', scene)
    scene = re.sub(r'[^\dА-ЯA-Z\-]', '', scene)
    return scene

def ensure_full_structure(result: Optional[Dict]) -> Dict:
    if result is None:
        return get_empty_structure()
    empty = get_empty_structure()
    filtered_result = {key: result.get(key, empty[key]) for key in empty.keys()}
    
    filtered_result["Персонажи"] = normalize_characters(filtered_result.get("Персонажи", []))
    filtered_result["Актеры"] = normalize_characters(filtered_result.get("Актеры", []))
    
    if filtered_result.get("Режим"):
        filtered_result["Режим"] = normalize_mode(filtered_result["Режим"])
    
    if filtered_result.get("Инт / нат"):
        filtered_result["Инт / нат"] = normalize_int_ext(filtered_result["Инт / нат"])
    
    if filtered_result.get("Сцена"):
        filtered_result["Сцена"] = normalize_scene_number(filtered_result["Сцена"])
    
    if not filtered_result.get("Актеры") and filtered_result.get("Персонажи"):
        filtered_result["Актеры"] = filtered_result["Персонажи"].copy()
    
    return filtered_result

@dataclass
class Scene:
    index: int
    scene_number_raw: Optional[str]
    episode: Optional[str]
    scene_number: Optional[str]
    day: Optional[str]
    heading_raw: str
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
    SCENE_NUM_PATTERN = re.compile(r'^(\d+)(?:-([\dА-ЯA-Z\-]+))?\.', re.IGNORECASE)
    DAY_PATTERN = re.compile(r'ДЕНЬ\s+(\d+)', re.IGNORECASE)
    EPISODE_PATTERN = re.compile(r'(\d+)\s+СЕЗОН\s+(\d+)\s+СЕРИЯ|(\d+)\s+СЕРИЯ', re.IGNORECASE)
    SCENE_START_PATTERN = re.compile(r'^(\d+)(?:-([\dА-ЯA-Z\-]+))?\.\s*', re.IGNORECASE | re.MULTILINE)
    
    def extract_scene_info(self, heading: str) -> Dict:
        info = {"scene_number_raw": None, "episode": None, "scene_number": None, "int_ext": None, "time_of_day": None}
        num_match = self.SCENE_NUM_PATTERN.match(heading)
        if num_match:
            first_num = num_match.group(1)
            second_part = num_match.group(2)
            
            if second_part:
                info["episode"] = first_num
                info["scene_number"] = second_part
                info["scene_number_raw"] = f"{first_num}-{second_part}"
            else:
                info["scene_number"] = first_num
                info["scene_number_raw"] = first_num
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
        return info
    
    def segment(self, text: str) -> List[Scene]:
        text = normalize_text_basic(text)
        episode_match = self.EPISODE_PATTERN.search(text)
        global_episode = None
        if episode_match:
            global_episode = episode_match.group(2) if episode_match.group(2) else episode_match.group(3)
        matches = list(self.SCENE_START_PATTERN.finditer(text))
        if not matches:
            logger.warning("Не найдено совпадений для разделения на сцены")
            return []
        logger.info(f"Найдено {len(matches)} потенциальных сцен для обработки")
        scenes = []
        current_day = None
        for i, match in enumerate(matches):
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            scene_text = text[start_pos:end_pos].strip()
            lines = scene_text.split('\n')
            if not lines:
                continue
            prev_text = text[:start_pos] if i == 0 else text[matches[i - 1].end():start_pos]
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
            if global_episode and not scene_info.get("episode"):
                scene_info["episode"] = global_episode
            scene = Scene(index=i, scene_number_raw=scene_info["scene_number_raw"], episode=scene_info.get("episode"),
                         scene_number=scene_info.get("scene_number"), day=current_day, heading_raw=heading,
                         int_ext=scene_info["int_ext"], time_of_day=scene_info["time_of_day"], body_raw=body)
            scenes.append(scene)
        logger.info(f"Разделение завершено: создано {len(scenes)} сцен")
        return scenes

def extract_json_from_output(output_text: str) -> Optional[Dict]:
    if not output_text:
        return None
    match = re.search(r"\{.*\}", output_text, re.DOTALL)
    if not match:
        return None
    json_str = match.group(0).strip()
    json_str = json_str.replace("'}", "\"}").replace("{'", "{\"")
    json_str = json_str.replace("':", "\":").replace(", '", ", \"")
    json_str = json_str.replace("['", "[\"").replace("']", "\"]")
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None

def extract_text_from_output(output):
    if isinstance(output, list) and len(output) > 0:
        return output[0].get("generated_text", "") if isinstance(output[0], dict) else str(output[0])
    elif isinstance(output, dict):
        return output.get("generated_text", "")
    return str(output)

def clean_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text

def extract_object_subobject(heading: str) -> Tuple[str, str]:
    heading_clean = heading
    num_match = re.match(r'^(\d+)(?:-([\dА-ЯA-Z\-]+))?\.\s*', heading, re.IGNORECASE)
    if num_match:
        heading_clean = heading[num_match.end():].strip()
    
    int_ext_match = re.search(r'\b(?:ИНТ|ЭКСТ|НАТ|ИНТЕРЬЕР|ЭКСТЕРЬЕР|ИНТ\.|ЭКСТ\.|НАТ\.|ИНТ\s|ЭКСТ\s|НАТ\s)\b', heading_clean, re.IGNORECASE)
    if int_ext_match:
        int_ext_pos = int_ext_match.end()
        while int_ext_pos < len(heading_clean) and heading_clean[int_ext_pos] in ['.', ' ']:
            int_ext_pos += 1
        heading_clean = heading_clean[int_ext_pos:].strip()
    
    time_match = re.search(r'\b(?:ДЕНЬ|НОЧЬ|УТРО|ВЕЧЕР|СУМЕРКИ|РАССВЕТ|НОЧЬЮ|ДНЕМ|ДНЁМ|ночью|днём)\b', heading_clean, re.IGNORECASE)
    if time_match:
        time_pos = heading_clean.upper().find(time_match.group(0).upper())
        if time_pos >= 0:
            heading_clean = heading_clean[:time_pos].strip()
    
    heading_clean = re.sub(r'\s+\d+\.?\s*$', '', heading_clean).strip()
    heading_clean = re.sub(r'[—–\-]+$', '', heading_clean).strip()
    heading_clean = re.sub(r'^[—–\-]+', '', heading_clean).strip()
    
    if '.' in heading_clean:
        parts = heading_clean.split('.', 1)
        object_part = re.sub(r'\s+', ' ', parts[0].strip()).strip()
        subobject_part = re.sub(r'\s+', ' ', parts[1].strip() if len(parts) > 1 else "").strip()
        subobject_part = re.sub(r'\.+$', '', subobject_part).strip()
        return object_part, subobject_part if subobject_part else ""
    else:
        return re.sub(r'\s+', ' ', heading_clean).strip(), ""

def extract_with_rules(scene: Scene, episode: str = "") -> Dict:
    if scene.episode:
        episode_value = scene.episode
    else:
        episode_value = episode
    scene_number_value = scene.scene_number if scene.scene_number else (scene.scene_number_raw if scene.scene_number_raw else "")
    
    object_part, subobject_part = extract_object_subobject(scene.heading_raw)
    
    result = {
        "День": scene.day or "",
        "Серия": f"Серия {episode_value}" if episode_value else episode,
        "Сцена": scene_number_value,
        "Объект": object_part,
        "Подобъект": subobject_part,
    }
    
    if scene.int_ext:
        result["Инт / нат"] = scene.int_ext
    
    if scene.time_of_day:
        time_normalized = normalize_mode(scene.time_of_day)
        if time_normalized:
            result["Режим"] = time_normalized
    
    return result

def build_prompt(scene: Scene, scene_text: str, episode: str) -> str:
    full_scene_text = f"Заголовок: {scene.heading_raw}\n\nТекст сцены:\n{scene_text}"
    context_parts = []
    if scene.day:
        context_parts.append(f"Контекст: ДЕНЬ {scene.day}")
    if episode:
        context_parts.append(f"Контекст: {episode}")
    if context_parts:
        full_scene_text = "\n".join(context_parts) + "\n\n" + full_scene_text
    return USER_PROMPT_TEMPLATE + f"\n\nТекст сцены:\n{full_scene_text}"

def extract_with_model(scene: Scene, scene_text: str, episode: str) -> Optional[Dict]:
    prompt = build_prompt(scene, scene_text, episode)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    try:
        try:
            output = pipe(messages, return_full_text=False, response_format={"type": "json_object"})
        except:
            output = pipe(messages, return_full_text=False)
        text = clean_text(extract_text_from_output(output))
        result = extract_json_from_output(text)
        if result:
            logger.info(f"Сцена {scene.index + 1}: успешно извлечен JSON")
            logger.debug(f"Сцена {scene.index + 1} JSON: {json.dumps(result, ensure_ascii=False, indent=2)}")
        else:
            logger.warning(f"Сцена {scene.index + 1}: не удалось извлечь JSON из ответа модели")
        return result
    except Exception as e:
        logger.error(f"Сцена {scene.index + 1}: ошибка при обработке моделью: {e}")
        return None

def extract_with_model_batch(scenes_data: List[Tuple[Scene, str, str]]) -> List[Optional[Dict]]:
    if not scenes_data:
        return []
    messages_batch = []
    for scene, scene_text, episode in scenes_data:
        prompt = build_prompt(scene, scene_text, episode)
        messages_batch.append([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}])
    try:
        try:
            outputs = pipe(messages_batch, return_full_text=False, batch_size=len(messages_batch), response_format={"type": "json_object"})
        except:
            outputs = pipe(messages_batch, return_full_text=False, batch_size=len(messages_batch))
        results = []
        for idx, (output, (scene, _, _)) in enumerate(zip(outputs, scenes_data)):
            text = clean_text(extract_text_from_output(output))
            result = extract_json_from_output(text)
            if result:
                logger.info(f"Сцена {scene.index + 1}: успешно извлечен JSON из батча")
                logger.debug(f"Сцена {scene.index + 1} JSON: {json.dumps(result, ensure_ascii=False, indent=2)}")
            else:
                logger.warning(f"Сцена {scene.index + 1}: не удалось извлечь JSON из ответа модели в батче")
            results.append(result)
        torch.cuda.empty_cache()
        gc.collect()
        return results
    except Exception as e:
        logger.error(f"Ошибка при батч-обработке: {e}")
        torch.cuda.empty_cache()
        gc.collect()
        return [None] * len(scenes_data)

def cascade_extract(scene: Scene, scene_text: str, episode: str, use_model: bool = True) -> Dict:
    rules_result = extract_with_rules(scene, episode)
    model_result = extract_with_model(scene, scene_text, episode) if use_model else None
    model_result = ensure_full_structure(model_result)
    final_result = {**model_result, **rules_result}
    return ensure_full_structure(final_result)

def read_docx_text(file_content: bytes) -> str:
    doc = Document(io.BytesIO(file_content))
    return "\n".join(p.text for p in doc.paragraphs)

async def process_and_stream_sse(text: str, episode: str):
    """
    Processes the script text and streams each scene result as a Server-Sent Event.
    """
    logger.info("Начало потоковой обработки текста")
    segmenter = SceneSegmenter()
    scenes = segmenter.segment(text)
    if not scenes:
        logger.warning("Сцены не найдены в тексте, поток завершается.")
        return

    logger.info(f"Найдено сцен для обработки: {len(scenes)}")
    
    if BATCH_SIZE > 1 and len(scenes) > 1 and tokenizer is not None:
        logger.info(f"Используется батчинг: размер батча {BATCH_SIZE}")
        scenes_data = [(scene, scene.heading_raw + "\n" + "\n".join(scene.body_raw), episode) for scene in scenes]
        for i in range(0, len(scenes_data), BATCH_SIZE):
            batch = scenes_data[i:i+BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(scenes_data) + BATCH_SIZE - 1) // BATCH_SIZE
            logger.info(f"Обработка батча {batch_num}/{total_batches} ({len(batch)} сцен)")
            try:
                # NOTE: This is a blocking call. For a high-performance server,
                # you might run this in a thread pool.
                # await asyncio.to_thread(extract_with_model_batch, batch)
                batch_results = extract_with_model_batch(batch)
                
                for j, (scene, _, _) in enumerate(batch):
                    model_result = batch_results[j]
                    if model_result:
                        logger.info(f"Сцена {scene.index + 1}: получен результат от модели")
                    rules_result = extract_with_rules(scene, episode)
                    model_result = ensure_full_structure(model_result)
                    result = {**model_result, **rules_result}
                    final_result = ensure_full_structure(result)
                    
                    yield f"data: {json.dumps(final_result, ensure_ascii=False)}\n\n"
                
                logger.info(f"Батч {batch_num} обработан успешно")
                await asyncio.sleep(0.01) # Yield control to the event loop

            except Exception as e:
                logger.error(f"Ошибка при обработке батча {batch_num}: {e}")
                # Optionally yield an error event for the scenes in the failed batch
                for scene, _, _ in batch:
                    error_data = {"error": f"Failed to process scene {scene.index + 1}", "details": str(e)}
                    yield f"event: error\ndata: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    else:
        logger.info("Используется последовательная обработка (без батчинга)")
        for scene in scenes:
            logger.info(f"Обработка сцены {scene.index + 1}/{len(scenes)}")
            scene_text = scene.heading_raw + "\n" + "\n".join(scene.body_raw)
            try:
                result = cascade_extract(scene, scene_text, episode, use_model=True)
                yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01) # Yield control
            except Exception as e:
                logger.error(f"Ошибка при обработке сцены {scene.index + 1}: {e}")
                error_data = {"error": f"Failed to process scene {scene.index + 1}", "details": str(e)}
                yield f"event: error\ndata: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    logger.info(f"Потоковая обработка завершена: обработано {len(scenes)} сцен")


logger.info("Загрузка модели...")
device = "cuda:0" if torch.cuda.is_available() else "cpu"
model_kwargs = {"dtype": torch.float16, "device_map": device, "trust_remote_code": True}
try:
    model_kwargs["attn_implementation"] = "flash_attention_2"
    logger.info("Flash Attention 2 включен")
except ImportError:
    logger.info("Flash Attention 2 недоступен, используется стандартное внимание")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, **model_kwargs)
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, max_new_tokens=MAX_NEW_TOKENS,
                temperature=0.1, do_sample=True, pad_token_id=tokenizer.eos_token_id)
torch.cuda.empty_cache()
gc.collect()
logger.info("Модель загружена!")


@app.post("/analyze")
async def analyze_script(file: UploadFile = File(...)):
    """
    Analyzes the script and streams the results back to the caller as Server-Sent Events.
    """
    if not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .docx")
    if not pipe:
        raise HTTPException(status_code=500, detail="Модель не загружена")
    try:
        file_content = await file.read()
        text = read_docx_text(file_content)
        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Файл пуст или не удалось прочитать текст")
        
        episode_match = re.search(r'(\d+)\s+СЕЗОН\s+(\d+)\s+СЕРИЯ|(\d+)\s+СЕРИЯ', text, re.IGNORECASE)
        episode = f"{episode_match.group(3) if episode_match and episode_match.group(3) else (episode_match.group(2) if episode_match else '')}" if episode_match else ""
        
        return StreamingResponse(process_and_stream_sse(text, episode), media_type="text/event-stream")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fatal error in /analyze endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
