"""
Фонетический транслитератор: английский текст → русское произношение.
Правила упорядочены от САМЫХ ДЛИННЫХ сочетаний к самым коротким.
"""

import re
from typing import Tuple

# ========== ПРАВИЛА ТРАНСЛИТЕРАЦИИ ==========
# Порядок КРИТИЧЕСКИ важен: длинные сочетания ПЕРВЫМИ!
# Формат: (regex, замена, контекст_до, контекст_после)

RULES: list[Tuple[str, str, str, str]] = [
    # ===== МНОГОБУКВЕННЫЕ СОЧЕТАНИЯ (4+) =====
    (r"ought", "от", "", ""),
    (r"aught", "от", "", ""),
    (r"eigh", "эй", "", ""),
    (r"ough", "оу", "", ""),
    (r"augh", "о", "", ""),
    
    # ===== ТРЁХБУКВЕННЫЕ СОЧЕТАНИЯ =====
    (r"tch", "ч", "", ""),
    (r"dge", "дж", "", ""),
    (r"tia", "ша", "", ""),
    (r"cia", "ша", "", ""),
    (r"sia", "жа", "", ""),
    (r"ssi", "ши", "", r"[aeiou]"),
    (r"sch", "ш", "", ""),
    (r"chr", "кр", "", ""),
    (r"thr", "тр", "", ""),
    (r"all", "ол", "", ""),
    (r"alk", "ок", "", ""),
    (r"ear", "ир", "", r"[^aeiou]"),
    (r"ear", "иэр", "", r"[aeiou]"),
    (r"eer", "ир", "", ""),
    
    # ===== TH =====
    (r"th", "з", r"[aeiou]", r"[aeiou]"),
    (r"th", "с", "", r"$"),
    (r"th", "т", r"[rst]", ""),
    (r"th", "з", "", ""),
    
    # ===== SH CH WH =====
    (r"sh", "ш", "", ""),
    (r"ch", "ч", "", ""),
    (r"wh", "в", "", r"[aeiou]"),
    (r"wh", "в", "", ""),
    (r"qu", "кв", "", ""),
    
    # ===== ДВУХБУКВЕННЫЕ ГЛАСНЫЕ =====
    (r"ee", "и", "", ""),
    (r"ea", "и", "", r"[^aeiou]r"),
    (r"ea", "э", "", ""),
    (r"oo", "у", "", r"[^aeiou]"),
    (r"oo", "о", "", r"r"),
    (r"ou", "ау", "", ""),
    (r"ow", "оу", "", r"$"),
    (r"ow", "ау", "", ""),
    (r"oi", "ой", "", ""),
    (r"oy", "ой", "", ""),
    
    # ===== ДВУХБУКВЕННЫЕ СОГЛАСНЫЕ =====
    (r"ck", "к", "", ""),
    (r"ph", "ф", "", ""),
    (r"gh", "", "", r"$"),
    (r"gh", "ф", "", ""),
    (r"ng", "нг", "", ""),
    
    # ===== Y =====
    (r"y", "ай", r"[^aeiou]s", r"[^aeiou]"),
    (r"y", "аи", r"^", r"[^aeiou]"),
    (r"y", "й", r"^", r"[aeiou]"),
    (r"y", "и", r"[^aeiou]s", r"$"),
    (r"y", "и", r"[^aeiou]", r"$"),
    (r"y", "и", "", r"[^aeiou]"),
    
    # ===== НЕПРОИЗНОСИМЫЕ =====
    (r"gh", "", "", r"t"),
    (r"k", "", "", r"n"),
    (r"w", "", "", r"r"),
    (r"p", "", "", r"s"),
    (r"b", "", r"m", r"$"),
    (r"b", "", r"m", r"[^aeiou]"),
    
    # ===== ОДИНОЧНЫЕ ГЛАСНЫЕ =====
    (r"a", "эй", r"[^aeiou]", r"[^aeiou]e$"),
    (r"a", "э", "", ""),
    (r"e", "и", r"", r"$"),
    (r"e", "э", "", ""),
    (r"i", "ай", r"[^aeiou]", r"[^aeiou]e$"),
    (r"i", "и", "", ""),
    (r"o", "оу", r"[^aeiou]", r"[^aeiou]e$"),
    (r"o", "о", "", ""),
    (r"u", "ю", r"[^aeiou]", r"[^aeiou]e[bdfgklmnprstv]"),
    (r"u", "а", "", ""),
    
    # ===== ОДИНОЧНЫЕ СОГЛАСНЫЕ =====
    (r"c", "с", "", r"[eiy]"),
    (r"c", "к", "", ""),
    (r"g", "дж", "", r"[eiy]"),
    (r"g", "г", "", ""),
    (r"s", "з", r"[aeiou]", r"[aeiou]"),
    (r"s", "с", "", ""),
    (r"j", "дж", "", ""),
    (r"x", "кс", "", ""),
    (r"q", "к", "", ""),
    (r"v", "в", "", ""),
    (r"w", "в", "", ""),
    (r"z", "з", "", ""),
]

# ========== КОНВЕРТАЦИЯ ЧИСЕЛ В ТЕКСТ ==========

_units_male = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_units_female = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
          "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
         "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
             "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_thousands = ["тысяча", "тысячи", "тысяч"]


def _triple_to_words(num: int, female: bool = False) -> str:
    if num == 0:
        return ""
    words = []
    units_list = _units_female if female else _units_male
    if num >= 100:
        words.append(_hundreds[num // 100])
        num %= 100
    if 10 <= num <= 19:
        words.append(_teens[num - 10])
    else:
        if num >= 20:
            words.append(_tens[num // 10])
            num %= 10
        if num > 0:
            words.append(units_list[num])
    return " ".join(words)


def _plural_form(n: int, forms: tuple) -> str:
    if n % 100 in (11, 12, 13, 14):
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    if n % 10 in (2, 3, 4):
        return forms[1]
    return forms[2]


def num_to_text(num_str: str) -> str:
    if not num_str:
        return num_str
    num_str = num_str.strip()
    if num_str.startswith("-"):
        return "минус " + num_to_text(num_str[1:])
    if "." in num_str:
        parts = num_str.split(".", 1)
        left = num_to_text(parts[0])
        right = " ".join(_units_female[int(d)] if d.isdigit() else d for d in parts[1])
        return f"{left} целых {right} десятых"
    num = int(num_str)
    if num == 0:
        return "ноль"
    words = []
    if num >= 1000:
        thousands = num // 1000
        if thousands == 1:
            words.append("тысяча")
        elif thousands == 2:
            words.append("две тысячи")
        else:
            words.append(f"{_triple_to_words(thousands, female=True)} {_plural_form(thousands, _thousands)}")
        num %= 1000
    if num > 0:
        words.append(_triple_to_words(num, female=False))
    return " ".join(words)


def normalize_numbers(text: str) -> str:
    def replace_num(match):
        if match.group(2):
            num = int(match.group(1))
            suffix = match.group(2)
            ordinals = {1: "первый", 2: "второй", 3: "третий", 4: "четвёртый", 5: "пятый"}
            return ordinals.get(num, num_to_text(match.group(1)) + "-й")
        return num_to_text(match.group(0))
    text = re.sub(r'(\d+)([-–](?:й|е|я|го|му|м))?', replace_num, text)
    return text


# ========== ЕДИНАЯ ФУНКЦИЯ ==========

def transliterate(text: str) -> str:
    """Транслитерирует текст: числа → текст, английские слова → русское произношение."""
    if not text:
        return text

    # Конвертируем числа
    text = normalize_numbers(text)

    # Транслитерируем английские фрагменты
    result = []
    words = re.split(r'([a-zA-Z]+)', text)

    for word in words:
        if not re.match(r'[a-zA-Z]+', word):
            result.append(word)
            continue

        word_lower = word.lower()
        is_all_caps = word.isupper()
        is_title = word[0].isupper() and not is_all_caps

        transformed = word_lower
        for pattern, replacement, before, after in RULES:
            full_pattern = before + "(" + pattern + ")" + after if before or after else pattern
            transformed = re.sub(full_pattern, replacement, transformed, flags=re.IGNORECASE)

        if is_all_caps:
            transformed = transformed.upper()
        elif is_title:
            transformed = transformed[0].upper() + transformed[1:] if transformed else transformed

        result.append(transformed)

    return "".join(result)


# ========== ТЕСТЫ ==========
if __name__ == "__main__":
    tests = [
        "Dark Souls",
        "Elden Ring",
        "Cyberpunk 2077",
        "Hollow Knight",
        "Twitch stream",
        "What the hell?",
        "1993 год",
        "2-й раз",
    ]
    print("=" * 60)
    print("ФОНЕТИЧЕСКИЙ ТРАНСЛИТЕРАТОР: ТЕСТЫ")
    print("=" * 60)
    for test in tests:
        result = transliterate(test)
        print(f"  {test:40s} → {result}")
    print("=" * 60)