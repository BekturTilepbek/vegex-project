#!/usr/bin/env python3
"""
VEGEX — сборка статического лендинга.

Пайплайн:
  content/<lang>.yaml  +  templates/  ->  Jinja2  ->  инлайн CSS/JS/шрифтов/фото
  ->  самодостаточные dist/<lang>/index.html без внешних зависимостей.

Запуск:  python build.py
"""

import base64
import io
import mimetypes
import re
import shutil
from pathlib import Path

import yaml
from PIL import Image
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
DIST = ROOT / "dist"

# Активные языки сборки. Приоритет — русский launch; английский включается
# добавлением "en" (контент в content/en.yaml). Переключатель RU/EN в шапке
# показывается автоматически, когда языков больше одного.
LANGS = ["ru"]

# Кириллица известная точка отказа при встраивании фото: имена файлов на
# кириллице ломают загрузку. Поэтому на этапе сборки транслитерируем в латиницу
# (решено в v3, не откатывать).
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(name: str) -> str:
    """Кириллица -> латиница + безопасные символы для имени файла."""
    out = []
    for ch in name.lower():
        out.append(TRANSLIT.get(ch, ch))
    slug = "".join(out)
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug).strip("-")
    return slug


def data_uri(path: Path) -> str:
    """Файл -> data: URI (base64)."""
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "application/octet-stream"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# Фото с профессиональной фотосессии приходят в исходном размере (часто
# 8-20 МБ на кадр). В git храним оригиналы как есть (static/images/), но перед
# base64-встраиванием в самодостаточный HTML пережимаем: ресайз по длинной
# стороне + JPEG качество ниже. Иначе итоговый dist/*.html раздувается до
# сотен МБ на одну страницу.
IMG_MAX_DIMENSION = 1800  # px по длинной стороне
IMG_JPEG_QUALITY = 78


def compressed_data_uri(path: Path) -> str:
    """Фото -> сжатый JPEG -> data: URI. Для не-растровых файлов — как есть."""
    if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        return data_uri(path)

    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        longest = max(w, h)
        if longest > IMG_MAX_DIMENSION:
            scale = IMG_MAX_DIMENSION / longest
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=IMG_JPEG_QUALITY, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"


def build_image_index() -> dict:
    """
    Индекс фото: транслитерированное имя (без расширения) -> data URI.
    Исходники хранятся в static/images/, готовый base64 в git не коммитим.
    """
    index = {}
    img_dir = STATIC / "images"
    if not img_dir.exists():
        return index
    for f in sorted(img_dir.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        key = translit(f.stem)
        index[key] = compressed_data_uri(f)
    return index


# unicode-диапазоны сабсетов (как у Google Fonts / fontsource) — чтобы браузер
# грузил кириллический файл только для кириллицы, латинский — для латиницы.
UNICODE_RANGE = {
    "cyrillic": "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",
    "latin": (
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
        "U+0304,U+0308,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,"
        "U+2212,U+2215,U+FEFF,U+FFFD"
    ),
}


def build_fonts_css() -> str:
    """
    Самодостаточные шрифты: инлайним Montserrat из static/fonts/ через @font-face
    (base64). Имя файла вида 'montserrat-<subset>-<weight>-normal.woff2', напр.
    'montserrat-cyrillic-700-normal.woff2' -> subset=cyrillic, weight=700.
    Если шрифтов нет — вернём пусто, и base.html подхватит <link> на Google Fonts.
    """
    fonts_dir = STATIC / "fonts"
    if not fonts_dir.exists():
        return ""
    blocks = []
    for f in sorted(fonts_dir.glob("*.woff2")):
        m = re.search(r"(cyrillic|latin)-(\d{3})", f.stem)
        if not m:
            continue
        subset, weight = m.group(1), m.group(2)
        urange = UNICODE_RANGE.get(subset)
        rng = f"unicode-range:{urange};" if urange else ""
        blocks.append(
            "@font-face{font-family:'Montserrat';font-style:normal;"
            f"font-weight:{weight};font-display:swap;"
            f"src:url({data_uri(f)}) format('woff2');{rng}}}"
        )
    return "\n".join(blocks)


def load_content(lang: str) -> dict:
    path = CONTENT / f"{lang}.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def make_env(images: dict) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def img(key: str):
        """В шаблоне: {{ img('imya-foto') }} -> data URI или None (тогда плейсхолдер)."""
        if not key:
            return None
        return images.get(translit(key))

    env.globals["img"] = img
    env.globals["has_img"] = lambda key: translit(key or "") in images
    return env


def render_lang(env: Environment, lang: str, css: str, js: str, fonts_css: str, fonts_present: bool):
    ctx = load_content(lang)
    ctx.update(
        {
            "lang": lang,
            "langs": LANGS,
            "css_inline": css,
            "js_inline": js,
            "fonts_css_inline": fonts_css,
            "fonts_inlined": fonts_present,
        }
    )
    html = env.get_template("base.html").render(**ctx)
    out_dir = DIST / lang
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    return len(html)


def main():
    if DIST.exists():
        shutil.rmtree(DIST)

    css = (STATIC / "css" / "main.css").read_text(encoding="utf-8")
    js = (STATIC / "js" / "main.js").read_text(encoding="utf-8")
    fonts_css = build_fonts_css()
    fonts_present = bool(fonts_css)
    images = build_image_index()

    env = make_env(images)

    print(f"Фото в индексе: {len(images)} | шрифты инлайн: {'да' if fonts_present else 'нет (Google Fonts fallback)'}")
    for lang in LANGS:
        size = render_lang(env, lang, css, js, fonts_css, fonts_present)
        print(f"  dist/{lang}/index.html — {size // 1024} КБ")

    # Корень -> основной язык (первый в списке). Нужен для Cloudflare Pages,
    # чтобы vegex.kg открывал язык по умолчанию.
    primary = LANGS[0]
    (DIST / "index.html").write_text(
        "<!DOCTYPE html><html lang=\"" + primary + "\"><head><meta charset=\"UTF-8\">"
        f"<meta http-equiv=\"refresh\" content=\"0; url=/{primary}/\">"
        f"<link rel=\"canonical\" href=\"/{primary}/\">"
        f"<title>VEGEX</title></head><body><a href=\"/{primary}/\">VEGEX</a></body></html>",
        encoding="utf-8",
    )
    print(f"  dist/index.html — редирект на /{primary}/")

    print("Готово.")


if __name__ == "__main__":
    main()
