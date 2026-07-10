#!/usr/bin/env python3
"""
VEGEX — сборка статического лендинга.

Пайплайн:
  content/<lang>.yaml  +  templates/  ->  Jinja2  ->  инлайн CSS/JS/шрифтов/фото
  ->  самодостаточные dist/<lang>/index.html без внешних зависимостей.

Запуск:  python build.py
"""

import base64
import mimetypes
import re
import shutil
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
DIST = ROOT / "dist"

LANGS = ["ru", "en"]

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
        index[key] = data_uri(f)
    return index


def build_fonts_css() -> str:
    """
    Самодостаточные шрифты: если в static/fonts/ лежат .woff2 Montserrat,
    инлайним их через @font-face (base64). Имя файла вида
    'Montserrat-700.woff2' -> weight 700. Если шрифтов нет — вернём пусто,
    и base.html подхватит запасной <link> на Google Fonts.
    """
    fonts_dir = STATIC / "fonts"
    if not fonts_dir.exists():
        return ""
    blocks = []
    for f in sorted(fonts_dir.glob("*.woff2")):
        m = re.search(r"(\d{3})", f.stem)
        weight = m.group(1) if m else "400"
        blocks.append(
            "@font-face{font-family:'Montserrat';font-style:normal;"
            f"font-weight:{weight};font-display:swap;"
            f"src:url({data_uri(f)}) format('woff2');}}"
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

    print("Готово.")


if __name__ == "__main__":
    main()
