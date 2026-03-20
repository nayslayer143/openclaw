#!/usr/bin/env python3
"""
Translate all Chinese strings in MiroFish frontend source to English.
Uses OpenAI API for accurate UI translation.
Creates .bak backups before modifying each file.
"""

import os, re, json, sys, shutil
from pathlib import Path
from openai import OpenAI

REPO_ROOT = Path(__file__).parent / "repo"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
BACKEND_SRC = REPO_ROOT / "backend" / "app"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
TRANSLATE_MODEL = os.environ.get("TRANSLATE_MODEL", "qwen2.5:7b")

client = OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)

CHINESE_RE = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+[^\n"\'`]*')

def has_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def translate_batch(strings):
    """Translate a list of Chinese strings to English in one API call."""
    if not strings:
        return {}

    prompt = """Translate these Chinese UI strings to concise English.
Return ONLY a JSON object mapping each original string to its English translation.
Keep translations short and suitable for UI labels/messages.
Preserve any format specifiers like {0}, %s, \\n etc.

Strings to translate:
""" + json.dumps(strings, ensure_ascii=False)

    response = client.chat.completions.create(
        model=TRANSLATE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    try:
        result = json.loads(response.choices[0].message.content)
        return result
    except:
        return {}

def translate_file(filepath):
    """Translate all Chinese strings in a file, create .bak backup first."""
    path = Path(filepath)
    content = path.read_text(encoding="utf-8")

    if not has_chinese(content):
        return False

    # Extract unique Chinese strings
    chinese_strings = list(set(re.findall(r'[\u4e00-\u9fff][^\n"\'`<>{}]{0,50}', content)))
    # Also get strings in quotes
    quoted = re.findall(r'["\']([^"\']*[\u4e00-\u9fff][^"\']*)["\']', content)
    chinese_strings = list(set(chinese_strings + quoted))
    chinese_strings = [s for s in chinese_strings if has_chinese(s)]

    if not chinese_strings:
        return False

    print(f"  Translating {len(chinese_strings)} strings in {path.name}...")

    # Translate in batches of 30
    translations = {}
    for i in range(0, len(chinese_strings), 30):
        batch = chinese_strings[i:i+30]
        translations.update(translate_batch(batch))

    # Backup original
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)

    # Apply translations (longest first to avoid partial replacements)
    new_content = content
    for zh, en in sorted(translations.items(), key=lambda x: -len(x[0])):
        if zh and en and zh != en:
            new_content = new_content.replace(zh, en)

    # Fix date locale
    new_content = new_content.replace("'zh-CN'", "'en-US'")

    path.write_text(new_content, encoding="utf-8")
    return True

def main():
    target_dirs = [FRONTEND_SRC]
    extensions = {".vue", ".js", ".ts"}

    files_changed = 0
    for target_dir in target_dirs:
        for ext in extensions:
            for filepath in sorted(target_dir.rglob(f"*{ext}")):
                if "node_modules" in str(filepath):
                    continue
                try:
                    if translate_file(filepath):
                        files_changed += 1
                        print(f"  Done: {filepath.relative_to(REPO_ROOT)}")
                except Exception as e:
                    print(f"  ERROR {filepath.name}: {e}")

    print(f"\nTranslated {files_changed} files. Originals saved as .bak")
    print("Restart MiroFish (npm run dev) to see changes.")

if __name__ == "__main__":
    main()
