"""
Placeholder module to simulate script processing.

In a production environment this module would interface with your
machine‑learning pipeline to analyse the contents of a film script and
extract the elements needed for preproduction planning.  Here we
generate a fixed table with sample data to illustrate the flow.
"""

from __future__ import annotations

import pandas as pd


def process_script(extract_dir: str, result_path: str) -> pd.DataFrame:
    """
    Simulate the analysis of a film script and return a table of scenes.

    Parameters
    ----------
    extract_dir: str
        The directory where the script files have been extracted.  This
        argument is ignored by the stub but kept for compatibility.
    result_path: str
        The path where the generated Excel workbook should be saved.

    Returns
    -------
    pd.DataFrame
        A DataFrame representing the table; it is also written to the
        given `result_path` as an XLSX file.
    """
    # Generate some dummy scenes.  In practice you would inspect the
    # extracted files under `extract_dir`, call a text analytics
    # pipeline and populate the table accordingly.
    data = [
        {
            "scene_number": 1,
            "location": "Кабинет",
            "time_of_day": "День",
            "main_characters": "Иван, Мария",
            "extras": "Секретарь",
            "props": "Стол, ноутбук",
            "special_effects": "Нет",
        },
        {
            "scene_number": 2,
            "location": "Улица",
            "time_of_day": "Ночь",
            "main_characters": "Петр, Анна",
            "extras": "Прохожие",
            "props": "Автомобиль",
            "special_effects": "Дым-машина",
        },
        {
            "scene_number": 3,
            "location": "Кафе",
            "time_of_day": "Утро",
            "main_characters": "Мария, Анна",
            "extras": "Официанты, клиенты",
            "props": "Чашки, меню",
            "special_effects": "Нет",
        },
    ]
    df = pd.DataFrame(data)
    # Write the table to an Excel file; openpyxl is used under the hood.
    df.to_excel(result_path, index=False)
    return df