import os
import sys
import re
import io
import json
import time
import hashlib
import urllib.parse
import urllib.request
import uuid as uuid_lib
import queue
import subprocess
import threading
import traceback
import tkinter as tk
from tkinter import ttk, messagebox

import minecraft_launcher_lib as mll

try:
    from PIL import Image, ImageDraw, ImageTk, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ==================== ПУТИ ====================
# В exe (--onefile) __file__ указывает во временную папку распаковки,
# поэтому для exe путь строим от самого исполняемого файла.
if getattr(sys, "frozen", False):
    PROJECT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== НАСТРОЙКИ ====================
GAME_DIR = os.path.join(PROJECT_DIR, "game")
MODS_DIR = os.path.join(GAME_DIR, "mods")
ICON_CACHE_DIR = os.path.join(GAME_DIR, ".icons")
ICON_FILE = os.path.join(PROJECT_DIR, "icon.ico")
INSTALLED_DB = os.path.join(GAME_DIR, "kotlauncher_mods.json")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")
DEFAULT_VERSION = "1.20.1"
LOADERS = ["Vanilla", "Fabric", "NeoForge"]
MOD_SOURCES = ["Modrinth", "CurseForge"]
INSTALL_RETRIES = 5      # сколько раз повторять установку при сетевых сбоях
RETRY_DELAY = 3          # пауза между попытками, секунды

MODRINTH_API = "https://api.modrinth.com/v2"
MODRINTH_HEADERS = {"User-Agent": "Kotlauncher/1.0"}

CF_API = "https://api.curseforge.com/v1"
CF_MIRROR = "https://api.curse.tools/v1/cf"   # публичное зеркало, работает без ключа
CF_GAME_ID = 432          # Minecraft
CF_CLASS_MOD = 6          # раздел «Моды»
CF_LOADER_IDS = {"fabric": 4, "neoforge": 6}

FABRIC_META = "https://meta.fabricmc.net/v2/versions/loader"
NEOFORGE_MAVEN_META = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
NEOFORGE_MAVEN_LATEST = "https://maven.neoforged.net/api/maven/latest/version/releases/net/neoforged/neoforge"
NEOFORGE_MAVEN_VERSIONS = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"

MOJANG_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FALLBACK_VERSIONS = ["1.21.4", "1.21.1", "1.20.6", "1.20.4", "1.20.1",
                     "1.19.4", "1.19.2", "1.18.2", "1.17.1", "1.16.5",
                     "1.15.2", "1.14.4", "1.12.2", "1.10.2", "1.8.9", "1.7.10"]

# Палитра тёмной темы (общая для всех окон)
BG_DARK = "#181820"
BG_PANEL = "#22222e"
BG_INPUT = "#2a2a38"
ACCENT = "#7c4dff"
ACCENT_HOVER = "#9a73ff"
GREEN = "#4caf50"
GREEN_HOVER = "#66bb6a"
BLUE = "#2f7fd1"
RED = "#ef5350"
PURPLE = "#7c4dff"
GRAY_BTN = "#55606e"
TEXT_MAIN = "#e8e8f0"
TEXT_DIM = "#9a9aa8"
ICON_SIZE = 32
# ===================================================


# ==================== ИКОНКА ЛАУНЧЕРА ====================

def generate_app_icon():
    """Рисует иконку лаунчера (лапа кота + буква K) и сохраняет icon.ico.

    Использует палитру темы. Если Pillow нет — пропускает без ошибок.
    """
    if not PIL_AVAILABLE or os.path.isfile(ICON_FILE):
        return

    BG = (24, 24, 32, 255)
    ACC_LIGHT = (154, 115, 255, 255)
    GRN = (76, 175, 80, 255)

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Скруглённый тёмный квадрат — фон
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=48, fill=BG)

    # Фиолетовое свечение под лапой
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([48, 58, 208, 218], fill=(124, 77, 255, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(20))
    img.alpha_composite(glow)

    # Лапа: подушечка + 4 пальца
    cx, cy = size // 2, size // 2 + 20
    pad_w, pad_h, toe_r = 95, 75, 22
    d.rounded_rectangle([cx - pad_w // 2, cy - pad_h // 2,
                         cx + pad_w // 2, cy + pad_h // 2],
                        radius=pad_h // 2 + pad_w // 6, fill=ACC_LIGHT)
    spread = pad_w * 0.62
    for dx, dy in [(-1.5, -0.85), (-0.5, -1.25), (0.5, -1.25), (1.5, -0.85)]:
        tx = cx + dx * spread * 0.5
        ty = cy + dy * pad_h * 0.55
        d.ellipse([tx - toe_r, ty - toe_r, tx + toe_r, ty + toe_r], fill=ACC_LIGHT)

    # Буква «K» поверх лапы
    ov = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle([102, 95, 122, 170], radius=7, fill=(255, 255, 255, 235))
    od.polygon([(124, 131), (161, 95), (171, 107), (134, 143)])
    od.polygon([(134, 135), (171, 170), (161, 179), (124, 145)])
    img.alpha_composite(ov)

    # Зелёная точка-индикатор внизу справа
    d.ellipse([196, 196, 226, 226], fill=GRN)

    try:
        img.save(ICON_FILE, sizes=[(16, 16), (24, 24), (32, 32),
                                   (48, 48), (64, 64), (128, 128), (256, 256)])
    except Exception:
        pass


# ==================== КОНФИГ ====================

def load_config() -> dict:
    defaults = {"cf_api_key": "", "ram_gb": 4, "java_path": ""}
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            defaults.update({k: v for k, v in data.items() if k in defaults})
        except Exception:
            pass
    return defaults


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


CONFIG = load_config()


def get_offline_uuid(username: str) -> str:
    """Оффлайн-UUID по нику — так же, как генерирует сам Minecraft в offline-режиме."""
    digest = hashlib.md5(("OfflinePlayer:" + username).encode("utf-8")).digest()
    b = bytearray(digest)
    b[6] = (b[6] & 0x0F) | 0x30   # версия 3 (md5)
    b[8] = (b[8] & 0x3F) | 0x80   # вариант RFC 4122
    return str(uuid_lib.UUID(bytes=bytes(b)))


def find_loader_version(mc_version: str, prefix: str) -> str | None:
    """Ищет установленное ядро по папке versions (через inheritsFrom в JSON)."""
    versions_dir = os.path.join(GAME_DIR, "versions")
    if not os.path.isdir(versions_dir):
        return None

    for name in os.listdir(versions_dir):
        version_json = os.path.join(versions_dir, name, name + ".json")
        if not os.path.isfile(version_json):
            continue
        try:
            with open(version_json, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        inherits = data.get("inheritsFrom", "")
        version_id = data.get("id", name)

        if version_id.startswith(prefix) and inherits == mc_version:
            return version_id

    for name in os.listdir(versions_dir):
        if name.startswith(prefix) and mc_version in name:
            return name

    return None


def load_installed_db() -> dict:
    if os.path.isfile(INSTALLED_DB):
        try:
            with open(INSTALLED_DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_installed_db(db: dict):
    with open(INSTALLED_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def clean_str(value, limit: int = 0) -> str:
    """Приводит значение к чистой однострочной строке для таблицы."""
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    value = value.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    value = value.replace("{", "(").replace("}", ")")
    value = " ".join(value.split())
    if limit and len(value) > limit:
        value = value[:limit].rstrip() + "…"
    return value


def fetch_json(url: str, headers: dict, timeout: int = 30):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str, headers: dict, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def run_with_retries(func, attempts: int, q, label: str):
    """Вызывает func, повторяя при сетевых сбоях.

    Уже скачанные файлы лаунчер-библиотека проверяет по хэшам и пропускает,
    поэтому повтор дёшев: докачивается только недокачанное.
    """
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                q.put(("log", f"Попытка {attempt} из {attempts}: {label}..."))
            func()
            return
        except Exception as e:
            last_err = e
            q.put(("log", f"Сбой при {label} ({type(e).__name__}), повторяем через {RETRY_DELAY} сек..."))
            time.sleep(RETRY_DELAY)
    raise last_err


# ==================== СПИСОК ВЕРСИЙ ====================

def fetch_release_versions() -> list[str]:
    """Качает официальный манифест Mojang напрямую, с таймаутом."""
    data = fetch_json(MOJANG_MANIFEST_URL, {"User-Agent": "Kotlauncher/1.0"}, timeout=15)
    versions = [v["id"] for v in data.get("versions", []) if v.get("type") == "release"]
    if not versions:
        raise RuntimeError("Манифест пуст")
    return versions


def fetch_fabric_loader_versions(mc_version: str) -> list[str]:
    """Список версий Fabric loader, совместимых с этой версией игры."""
    ua = {"User-Agent": "Kotlauncher/1.0"}
    try:
        url = FABRIC_META + "/" + urllib.parse.quote(mc_version)
        data = fetch_json(url, ua)
        versions = []
        for item in data:
            v = (item.get("loader") or {}).get("version")
            if v and v not in versions:
                versions.append(v)
        if versions:
            return versions
    except Exception:
        pass
    # Запасной путь: общий список loader (он не зависит от версии игры)
    try:
        data = fetch_json(FABRIC_META, ua)
        versions = []
        for item in data:
            v = (item.get("loader") or {}).get("version")
            if v and v not in versions:
                versions.append(v)
        return versions
    except Exception:
        return []


def _neoforge_prefix(mc_version: str) -> str:
    """NeoForge нумерует свои сборки по версии игры: 1.21.1 -> 21.1.x."""
    if mc_version == "1.20.1":
        return "1.20.1-"   # старая ветка живёт в пакете forge
    return mc_version[2:] + "."


def fetch_neoforge_versions(mc_version: str) -> list[str]:
    """Список сборок NeoForge для этой версии игры (новые сверху)."""
    ua = {"User-Agent": "Kotlauncher/1.0"}
    prefix = _neoforge_prefix(mc_version)

    # Основной путь: JSON-API maven.neoforged.net
    try:
        data = fetch_json(NEOFORGE_MAVEN_VERSIONS, ua)
        if isinstance(data, dict):
            data = data.get("versions", [])
        versions = [str(v).strip() for v in data
                    if isinstance(v, str) and v.strip().startswith(prefix)]
        versions.reverse()
        if versions:
            return versions
    except Exception:
        pass

    # Запасной путь 1: XML метаданные maven (парсим как текст, а не JSON)
    try:
        xml_text = fetch_text(NEOFORGE_MAVEN_META, ua)
        versions = [v.strip() for v in re.findall(r"<version>([^<]+)</version>", xml_text)
                    if v.strip().startswith(prefix)]
        versions.reverse()
        if versions:
            return versions
    except Exception:
        pass

    # Запасной путь 2: последняя стабильная сборка через API latest
    try:
        url = NEOFORGE_MAVEN_LATEST + "?filter=" + urllib.parse.quote(prefix.rstrip("."))
        raw = fetch_text(url, ua).strip()
        if raw:
            return [raw]
    except Exception:
        pass

    return []


# ==================== ИКОНКИ МОДОВ ====================

def download_icon_to_cache(url: str) -> str | None:
    """Скачивает иконку мода в кэш и возвращает путь к PNG-файлу (или None)."""
    if not url:
        return None

    os.makedirs(ICON_CACHE_DIR, exist_ok=True)
    dest = os.path.join(ICON_CACHE_DIR, hashlib.sha1(url.encode()).hexdigest() + ".png")
    if os.path.isfile(dest):
        return dest

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Kotlauncher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except Exception:
        return None

    if PIL_AVAILABLE:
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            img.thumbnail((ICON_SIZE, ICON_SIZE))
            img.save(dest, "PNG")
            return dest
        except Exception:
            return None

    lower = url.lower()
    if lower.endswith(".png") or lower.endswith(".gif"):
        raw_dest = os.path.join(ICON_CACHE_DIR,
                                hashlib.sha1(url.encode()).hexdigest() + os.path.splitext(lower)[1])
        with open(raw_dest, "wb") as f:
            f.write(raw)
        return raw_dest
    return None


# ==================== MODRINTH API ====================

def modrinth_get(path_with_query: str):
    return fetch_json(MODRINTH_API + path_with_query, MODRINTH_HEADERS)


def modrinth_search(query: str, mc_version: str, loader_category: str, limit: int = 40):
    facets = json.dumps([
        ["project_type:mod"],
        ["categories:" + loader_category],
        ["versions:" + mc_version],
    ])
    params = urllib.parse.urlencode({
        "query": query,
        "limit": limit,
        "index": "downloads",
        "facets": facets,
    })
    data = modrinth_get("/search?" + params)
    return data.get("hits", [])


def modrinth_versions(pid: str, mc_version: str, loader: str):
    q = urllib.parse.quote(json.dumps([loader]))
    gv = urllib.parse.quote(json.dumps([mc_version]))
    return modrinth_get(f"/project/{pid}/version?loaders={q}&game_versions={gv}")


def modrinth_download_file(file_info: dict, dest_dir: str, q) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    url = file_info["url"]
    filename = os.path.basename(file_info["filename"])
    dest = os.path.join(dest_dir, filename)

    if os.path.isfile(dest):
        q.put(("log", f"  Уже скачан: {filename}"))
        return dest

    q.put(("log", f"  Скачиваем: {filename}"))
    req = urllib.request.Request(url, headers=MODRINTH_HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        out.write(resp.read())

    expected = (file_info.get("hashes") or {}).get("sha1")
    if expected:
        h = hashlib.sha1()
        with open(dest, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        if h.hexdigest() != expected:
            os.remove(dest)
            raise RuntimeError(f"Файл {filename} повреждён (не совпал sha1)")
    return dest


def install_mod_recursive(pid: str, mc_version: str, loader: str,
                          q, visited: set, db: dict, is_root: bool = False,
                          force_version: str | None = None):
    """Ставит мод Modrinth и все его обязательные зависимости рекурсивно.

    force_version — конкретная версия мода (version_number), если пользователь
    выбрал её вручную; действует только на корневой мод.
    """
    if pid in visited:
        return
    visited.add(pid)

    versions = modrinth_versions(pid, mc_version, loader)
    if not versions:
        if is_root:
            raise RuntimeError("Для этой версии игры и ядра нет подходящих версий мода.")
        return

    version = None
    if force_version and is_root:
        for v in versions:
            if v.get("version_number") == force_version or v.get("id") == force_version:
                version = v
                break
        if version is None:
            raise RuntimeError(f"Выбранная версия {force_version} не найдена.")

    if version is None:
        version = versions[0]

    project_info = modrinth_get(f"/project/{pid}")
    title = project_info.get("title", pid)

    files = version.get("files", [])
    file_info = next((f for f in files if f.get("primary")), files[0] if files else None)
    if not file_info:
        if is_root:
            raise RuntimeError(f"У мода {title} нет файлов для скачивания.")
        return

    if pid in db:
        q.put(("log", f"  {title} уже установлен — пропускаем."))
    else:
        if is_root:
            q.put(("log", f"Устанавливаем мод: {title} ({version.get('version_number', '')})"))
        else:
            q.put(("log", f"Устанавливаем зависимость: {title}"))
        modrinth_download_file(file_info, MODS_DIR, q)
        db[pid] = file_info["filename"]
        save_installed_db(db)

    for dep in version.get("dependencies", []):
        if dep.get("dependency_type") == "required" and dep.get("project_id"):
            install_mod_recursive(dep["project_id"], mc_version, loader, q, visited, db)


# ==================== CURSEFORGE API ====================

def cf_headers() -> dict:
    return {
        "x-api-key": CONFIG.get("cf_api_key", ""),
        "Accept": "application/json",
        "User-Agent": "Kotlauncher/1.0",
    }


def cf_get(path_with_query: str):
    """Запрос к CurseForge: сначала публичные зеркала (без ключа),
    затем официальный API с ключом из настроек."""
    mirrors = [CF_MIRROR]
    for mirror in mirrors:
        try:
            return fetch_json(mirror + path_with_query,
                              {"User-Agent": "Kotlauncher/1.0"})
        except Exception:
            continue
    key = CONFIG.get("cf_api_key", "")
    if not key:
        raise RuntimeError(
            "Зеркало CurseForge не отвечает. Варианты:\n"
            "1) вставь свой ключ в Настройках (бесплатный, с console.curseforge.com);\n"
            "2) пользуйся источником Modrinth — он работает без ключей всегда.")
    return fetch_json(CF_API + path_with_query, cf_headers())


def cf_search(query: str, mc_version: str, loader: str, limit: int = 40):
    """Поиск модов на CurseForge. loader — 'fabric' или 'neoforge'."""
    params = urllib.parse.urlencode({
        "gameId": CF_GAME_ID,
        "classId": CF_CLASS_MOD,
        "searchFilter": query,
        "gameVersion": mc_version,
        "modLoaderType": CF_LOADER_IDS[loader],
        "sortField": 2,        # популярность
        "sortDescending": "true",
        "pageSize": limit,
    })
    data = cf_get("/mods/search?" + params)
    return data.get("data", [])


def cf_get_mod(mod_id: int):
    return cf_get(f"/mods/{mod_id}").get("data", {})


def cf_files(mod_id: int):
    return cf_get(f"/mods/{mod_id}/files?pageIndex=0&pageSize=20").get("data", [])


def cf_pick_file(files: list, mc_version: str):
    """Выбирает свежий файл, совместимый с версией игры."""
    for f in files:
        if mc_version in (f.get("gameVersions") or []):
            return f
    return None


def cf_file_details(mod_id: int, file_id: int):
    return cf_get(f"/mods/{mod_id}/files/{file_id}").get("data", {})


def cf_download(file_info: dict, mod_id: int, dest_dir: str, q) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    filename = os.path.basename(file_info.get("fileName") or "mod.jar")
    url = file_info.get("downloadUrl")
    if not url:
        url = f"https://www.curseforge.com/api/v1/mods/{mod_id}/files/{file_info['id']}/download"
        filename = file_info.get("fileName", filename)
    dest = os.path.join(dest_dir, filename)

    if os.path.isfile(dest):
        q.put(("log", f"  Уже скачан: {filename}"))
        return dest

    q.put(("log", f"  Скачиваем: {filename}"))
    req = urllib.request.Request(url, headers={"User-Agent": "Kotlauncher/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        out.write(resp.read())

    # Проверка sha1, если CurseForge её прислал (algo == 1)
    expected = None
    for hsh in file_info.get("hashes") or []:
        if hsh.get("algo") == 1:
            expected = hsh.get("value")
            break
    if expected:
        h = hashlib.sha1()
        with open(dest, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        if h.hexdigest() != expected:
            os.remove(dest)
            raise RuntimeError(f"Файл {filename} повреждён (не совпал sha1)")
    return dest


def install_mod_recursive_cf(mod_id: int, mc_version: str,
                             q, visited: set, db: dict, is_root: bool = False,
                             force_file_id=None):
    """Ставит мод CurseForge и обязательные зависимости рекурсивно.

    force_file_id — конкретный файл (его id), если пользователь выбрал
    версию вручную; действует только на корневой мод.
    """
    if mod_id in visited:
        return
    visited.add(mod_id)

    db_key = f"cf:{mod_id}"

    mod = cf_get_mod(mod_id)
    title = clean_str(mod.get("name", str(mod_id)), 60)

    files = cf_files(mod_id)

    file_info = None
    if force_file_id and is_root:
        for f in files:
            if f.get("id") == force_file_id:
                file_info = f
                break
        if file_info is None:
            raise RuntimeError(f"Выбранный файл мода {title} не найден.")

    if file_info is None:
        file_info = cf_pick_file(files, mc_version)
    if not file_info:
        if is_root:
            raise RuntimeError(f"Для {mc_version} нет подходящих файлов мода {title}.")
        return

    if db_key in db:
        q.put(("log", f"  {title} уже установлен — пропускаем."))
    else:
        if is_root:
            q.put(("log", f"Устанавливаем мод: {title} ({file_info.get('displayName') or file_info.get('fileName', '')})"))
        else:
            q.put(("log", f"Устанавливаем зависимость: {title}"))
        cf_download(file_info, mod_id, MODS_DIR, q)
        db[db_key] = file_info.get("fileName", "")
        save_installed_db(db)

    # Обязательные зависимости (relationType == 3)
    details = cf_file_details(mod_id, file_info["id"])
    for dep in details.get("dependencies") or []:
        if dep.get("relationType") == 3 and dep.get("modId"):
            install_mod_recursive_cf(dep["modId"], mc_version, q, visited, db)


# ======================================================


class DarkThemeMixin:
    """Общие элементы тёмной темы для всех окон."""

    def setup_dark_styles(self, widget):
        style = ttk.Style(widget)
        style.theme_use("clam")

        style.configure("Dark.TCombobox",
                        fieldbackground=BG_INPUT, background=BG_INPUT,
                        foreground=TEXT_MAIN, arrowcolor=TEXT_DIM,
                        bordercolor=BG_PANEL, lightcolor=BG_PANEL,
                        darkcolor=BG_PANEL, borderwidth=0, padding=6)
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", BG_INPUT)],
                  foreground=[("readonly", TEXT_MAIN)])
        widget.option_add("*TCombobox*Listbox.background", BG_INPUT)
        widget.option_add("*TCombobox*Listbox.foreground", TEXT_MAIN)
        widget.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        widget.option_add("*TCombobox*Listbox.selectForeground", "white")

        style.configure("Dark.Horizontal.TProgressbar",
                        background=ACCENT, troughcolor=BG_INPUT,
                        bordercolor=BG_DARK, lightcolor=ACCENT,
                        darkcolor=ACCENT, thickness=8)

        style.configure("Dark.TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("Dark.TNotebook.Tab", background=BG_PANEL, foreground=TEXT_DIM,
                        padding=(18, 8), font=("Arial", 10, "bold"))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])

        style.configure("Dark.Treeview",
                        background=BG_PANEL, foreground=TEXT_MAIN,
                        fieldbackground=BG_PANEL, rowheight=40,
                        font=("Consolas", 9), borderwidth=0)
        style.configure("Dark.Treeview.Heading",
                        background=BG_INPUT, foreground=TEXT_DIM,
                        font=("Arial", 9, "bold"), borderwidth=0, padding=(6, 6))
        style.map("Dark.Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])

        style.configure("Dark.Vertical.TScrollbar",
                        background=BG_INPUT, troughcolor=BG_DARK,
                        bordercolor=BG_DARK, arrowcolor=TEXT_DIM)

        return style

    def apply_window_icon(self, window):
        """Ставит иконку на окно (иконку лаунчера)."""
        try:
            if os.path.isfile(ICON_FILE):
                window.iconbitmap(ICON_FILE)
        except Exception:
            pass

    def make_button(self, parent, text, bg, command, width=16, font_size=10,
                    hover_color=None):
        btn = tk.Button(parent, text=text, bg=bg, fg="white",
                        activebackground=hover_color or ACCENT_HOVER,
                        activeforeground="white",
                        relief="flat", borderwidth=0, cursor="hand2",
                        font=("Arial", font_size, "bold"), width=width,
                        command=command)
        hover = hover_color or ACCENT_HOVER
        btn.bind("<Enter>", lambda e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def make_entry(self, parent, width=None, show=None):
        kwargs = dict(font=("Arial", 11), bg=BG_INPUT, fg=TEXT_MAIN,
                      relief="flat", insertbackground=TEXT_MAIN)
        if width:
            kwargs["width"] = width
        if show:
            kwargs["show"] = show
        return tk.Entry(parent, **kwargs)


class VersionPickDialog(DarkThemeMixin):
    """Диалог выбора версии мода: список строк, двойной клик или ОК."""

    def __init__(self, parent_window, entries, on_choose):
        self.on_choose = on_choose
        self.win = tk.Toplevel(parent_window)
        self.win.title("Kotlauncher — Выбор версии")
        self.win.geometry("560x460")
        self.win.resizable(False, False)
        self.win.configure(bg=BG_DARK)
        self.win.grab_set()
        self.win.transient(parent_window)

        self.setup_dark_styles(self.win)
        self.apply_window_icon(self.win)

        tk.Label(self.win, text="Выбери версию мода", font=("Arial", 14, "bold"),
                 bg=BG_DARK, fg=TEXT_MAIN).pack(pady=(14, 8))

        tk.Label(self.win, text="Галочка — файл совместим с выбранной версией игры",
                 font=("Arial", 8), bg=BG_DARK, fg=TEXT_DIM).pack()

        frame = tk.Frame(self.win, bg=BG_DARK)
        frame.pack(fill="both", expand=True, padx=16, pady=10)

        self.listbox = tk.Listbox(frame, font=("Consolas", 10),
                                  bg=BG_INPUT, fg=TEXT_MAIN,
                                  selectbackground=ACCENT, selectforeground="white",
                                  activestyle="none", highlightthickness=0,
                                  borderwidth=0)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview,
                               style="Dark.Vertical.TScrollbar")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._payloads = []
        for label, payload in entries:
            self.listbox.insert("end", label)
            self._payloads.append(payload)
        if self._payloads:
            self.listbox.selection_set(0)
        self.listbox.bind("<Double-1>", lambda e: self._confirm())

        btns = tk.Frame(self.win, bg=BG_DARK)
        btns.pack(fill="x", pady=(0, 14))
        self.make_button(btns, "Выбрать", GREEN, self._confirm,
                         width=14, hover_color=GREEN_HOVER).pack(side="left", padx=16)
        self.make_button(btns, "Отмена", GRAY_BTN, self.win.destroy,
                         width=10).pack(side="left")

    def _confirm(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        payload = self._payloads[selection[0]]
        self.win.destroy()
        self.on_choose(payload)


class SettingsWindow(DarkThemeMixin):
    """Окно настроек лаунчера в тёмной теме."""

    def __init__(self, app: "LauncherApp"):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Kotlauncher — Настройки")
        self.win.geometry("520x440")
        self.win.resizable(False, False)
        self.win.configure(bg=BG_DARK)
        self.win.grab_set()

        self.setup_dark_styles(self.win)
        self.apply_window_icon(self.win)
        self._build_ui()

    def _build_ui(self):
        tk.Label(self.win, text="⚙ Настройки", font=("Arial", 16, "bold"),
                 bg=BG_DARK, fg=TEXT_MAIN).pack(pady=(16, 10))

        panel = tk.Frame(self.win, bg=BG_PANEL)
        panel.pack(fill="both", expand=True, padx=16)

        inner = tk.Frame(panel, bg=BG_PANEL)
        inner.pack(fill="both", expand=True, padx=16, pady=14)

        tk.Label(inner, text="Ключ API CurseForge (запасной вариант)",
                 font=("Arial", 10, "bold"),
                 bg=BG_PANEL, fg=TEXT_MAIN, anchor="w").pack(fill="x")
        self.entry_cf_key = self.make_entry(inner, show="*")
        self.entry_cf_key.pack(fill="x", ipady=6, pady=(2, 2))
        self.entry_cf_key.insert(0, CONFIG.get("cf_api_key", ""))

        tk.Label(inner,
                 text="Поиск работает и без ключа — через публичное зеркало.\n"
                      "Ключ (бесплатный, с console.curseforge.com) нужен,\n"
                      "только если зеркало однажды перестанет отвечать.",
                 font=("Arial", 8), bg=BG_PANEL, fg=TEXT_DIM,
                 anchor="w", justify="left").pack(fill="x", pady=(0, 12))

        tk.Label(inner, text="Оперативная память для игры (ГБ)", font=("Arial", 10, "bold"),
                 bg=BG_PANEL, fg=TEXT_MAIN, anchor="w").pack(fill="x")
        self.spin_ram = tk.Spinbox(inner, from_=2, to=16, width=8,
                                   font=("Arial", 11), bg=BG_INPUT, fg=TEXT_MAIN,
                                   buttonbackground=BG_INPUT, buttoncursor="hand2",
                                   relief="flat", insertbackground=TEXT_MAIN)
        self.spin_ram.pack(anchor="w", pady=(2, 12))
        self.spin_ram.delete(0, "end")
        self.spin_ram.insert(0, str(CONFIG.get("ram_gb", 4)))

        tk.Label(inner, text="Путь к java.exe (необязательно)", font=("Arial", 10, "bold"),
                 bg=BG_PANEL, fg=TEXT_MAIN, anchor="w").pack(fill="x")
        self.entry_java = self.make_entry(inner)
        self.entry_java.pack(fill="x", ipady=6, pady=(2, 12))
        self.entry_java.insert(0, CONFIG.get("java_path", ""))

        tk.Label(inner,
                 text="Если не указан — используется системная Java.\n"
                      "Больше памяти = меньше лагов, но не ставь больше\n"
                      "половины всей оперативки компьютера.",
                 font=("Arial", 8), bg=BG_PANEL, fg=TEXT_DIM,
                 anchor="w", justify="left").pack(fill="x", pady=(0, 14))

        btns = tk.Frame(self.win, bg=BG_DARK)
        btns.pack(fill="x", pady=(8, 14))
        self.make_button(btns, "💾  Сохранить", GREEN, self.on_save,
                         width=16, font_size=11,
                         hover_color=GREEN_HOVER).pack(side="left", padx=16)
        self.make_button(btns, "Отмена", GRAY_BTN, self.win.destroy,
                         width=10).pack(side="left", padx=4)
        self.label_save_status = tk.Label(btns, text="", font=("Arial", 9),
                                          bg=BG_DARK, fg=TEXT_DIM)
        self.label_save_status.pack(side="left", padx=12)

    def on_save(self):
        key = self.entry_cf_key.get().strip()
        try:
            ram = int(self.spin_ram.get())
        except ValueError:
            ram = 4
        ram = max(2, min(16, ram))
        java = self.entry_java.get().strip()

        CONFIG["cf_api_key"] = key
        CONFIG["ram_gb"] = ram
        CONFIG["java_path"] = java
        save_config(CONFIG)

        self.label_save_status.config(text="✓ Сохранено", fg="#7bd88f")
        self.win.after(1200, self.win.destroy)


class ModsWindow(DarkThemeMixin):
    """Окно менеджера модов: Modrinth + CurseForge, иконки, выбор версии мода."""

    def __init__(self, app: "LauncherApp"):
        self.app = app
        self.results = []
        self.db = load_installed_db()
        self._row_icons = []
        self._iid_to_index = {}
        self._photo_ready = {}
        self._desc_photo = None
        self._version_choice = {}   # pid_key -> выбранная вручную версия мода

        self.win = tk.Toplevel(app.root)
        self.win.title("Kotlauncher — Моды")
        self.win.geometry("880x660")
        self.win.resizable(False, False)
        self.win.configure(bg=BG_DARK)
        self.win.grab_set()

        self.setup_dark_styles(self.win)
        self.apply_window_icon(self.win)
        self._build_ui()
        self._refresh_installed()
        self._auto_search()

    def _build_ui(self):
        version = self.app.combo_version.get() or DEFAULT_VERSION
        loader = self.app.combo_loader.get()

        header = tk.Frame(self.win, bg=BG_DARK)
        header.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(header, text="🧩 Менеджер модов", font=("Arial", 16, "bold"),
                 bg=BG_DARK, fg=TEXT_MAIN).pack(side="left")

        badges = tk.Frame(header, bg=BG_DARK)
        badges.pack(side="right")
        for text, color in ((f"Minecraft {version}", ACCENT),
                            (f"Ядро: {loader}", GREEN if loader != "Vanilla" else RED)):
            badge = tk.Label(badges, text=text, font=("Arial", 9, "bold"),
                             bg=BG_INPUT, fg=color, padx=10, pady=4)
            badge.pack(side="left", padx=4)

        if loader == "Vanilla":
            tk.Label(self.win,
                     text="⚠  Моды работают только с ядрами Fabric и NeoForge — выбери ядро в главном окне",
                     font=("Arial", 9), bg=BG_DARK, fg=RED).pack(fill="x", padx=16)

        search_frame = tk.Frame(self.win, bg=BG_DARK)
        search_frame.pack(fill="x", padx=16, pady=10)

        self.combo_source = ttk.Combobox(search_frame, width=11, state="readonly",
                                         values=MOD_SOURCES, font=("Arial", 9),
                                         style="Dark.TCombobox")
        self.combo_source.set(MOD_SOURCES[0])
        self.combo_source.pack(side="left", padx=(0, 8))

        self.entry_search = self.make_entry(search_frame)
        self.entry_search.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        self.entry_search.bind("<Return>", lambda e: self.on_search())
        self.entry_search.bind("<FocusIn>", self._clear_placeholder)
        self.entry_search.bind("<FocusOut>", self._set_placeholder)
        self._set_placeholder()
        self.make_button(search_frame, "🔍  Найти", ACCENT, self.on_search,
                         width=10).pack(side="left")

        self.notebook = ttk.Notebook(self.win, style="Dark.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=16)

        # --- вкладка «Каталог» ---
        catalog = tk.Frame(self.notebook, bg=BG_DARK)
        self.notebook.add(catalog, text="  🔍 Каталог  ")

        table_frame = tk.Frame(catalog, bg=BG_DARK)
        table_frame.pack(fill="both", expand=True, padx=8, pady=8)

        columns = ("name", "author", "downloads", "desc")
        self.tree = ttk.Treeview(table_frame, columns=columns,
                                 show="tree headings", style="Dark.Treeview")
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=56, minwidth=56, stretch=False)
        self.tree.heading("name", text="Название")
        self.tree.heading("author", text="Автор")
        self.tree.heading("downloads", text="Скачиваний")
        self.tree.heading("desc", text="Описание")
        self.tree.column("name", width=210, anchor="w")
        self.tree.column("author", width=120, anchor="w")
        self.tree.column("downloads", width=95, anchor="e")
        self.tree.column("desc", width=270, anchor="w")

        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview,
                               style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select_mod)
        self.tree.bind("<Double-1>", lambda e: self.on_install())
        self.tree.tag_configure("installed", foreground="#7bd88f")
        self.tree.tag_configure("normal", foreground=TEXT_MAIN)

        desc_frame = tk.Frame(catalog, bg=BG_PANEL)
        desc_frame.pack(fill="x", padx=8, pady=(0, 8))

        desc_inner = tk.Frame(desc_frame, bg=BG_PANEL)
        desc_inner.pack(fill="x", padx=12, pady=8)

        self.label_desc_icon = tk.Label(desc_inner, text="", bg=BG_PANEL, anchor="n")
        self.label_desc_icon.pack(side="left", padx=(0, 10))

        desc_text_frame = tk.Frame(desc_inner, bg=BG_PANEL)
        desc_text_frame.pack(side="left", fill="both", expand=True)

        self.label_mod_title = tk.Label(desc_text_frame, text="Выбери мод в списке",
                                        font=("Arial", 10, "bold"),
                                        bg=BG_PANEL, fg=TEXT_MAIN, anchor="w")
        self.label_mod_title.pack(fill="x")

        self.label_version_choice = tk.Label(desc_text_frame, text="",
                                             font=("Arial", 9),
                                             bg=BG_PANEL, fg=ACCENT_HOVER, anchor="w")
        self.label_version_choice.pack(fill="x")

        self.text_desc = tk.Text(desc_text_frame, height=3, font=("Arial", 9),
                                 bg=BG_PANEL, fg=TEXT_DIM, relief="flat",
                                 wrap="word", state="disabled", borderwidth=0)
        self.text_desc.pack(fill="x", pady=(2, 0))

        catalog_btns = tk.Frame(catalog, bg=BG_DARK)
        catalog_btns.pack(fill="x", padx=8, pady=(0, 10))
        self.btn_install = self.make_button(catalog_btns, "⬇  Установить выбранный",
                                            GREEN, self.on_install, width=22, font_size=11,
                                            hover_color=GREEN_HOVER)
        self.btn_install.pack(side="left")
        self.btn_other_version = self.make_button(catalog_btns, "Другая версия...",
                                                  GRAY_BTN, self.on_pick_version,
                                                  width=16)
        self.btn_other_version.pack(side="left", padx=8)
        self.catalog_status = tk.Label(catalog_btns, text="", font=("Arial", 9),
                                       bg=BG_DARK, fg=TEXT_DIM)
        self.catalog_status.pack(side="left", padx=4)

        # --- вкладка «Установленные» ---
        installed_tab = tk.Frame(self.notebook, bg=BG_DARK)
        self.notebook.add(installed_tab, text="  📦 Установленные  ")

        inst_table_frame = tk.Frame(installed_tab, bg=BG_DARK)
        inst_table_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.tree_installed = ttk.Treeview(inst_table_frame,
                                           columns=("file",), show="headings",
                                           style="Dark.Treeview")
        self.tree_installed.heading("file", text="Файл мода")
        self.tree_installed.column("file", width=750, anchor="w")

        inst_scroll = ttk.Scrollbar(inst_table_frame, orient="vertical",
                                    command=self.tree_installed.yview,
                                    style="Dark.Vertical.TScrollbar")
        self.tree_installed.configure(yscrollcommand=inst_scroll.set)
        self.tree_installed.pack(side="left", fill="both", expand=True)
        inst_scroll.pack(side="right", fill="y")

        inst_btns = tk.Frame(installed_tab, bg=BG_DARK)
        inst_btns.pack(fill="x", padx=8, pady=(0, 10))
        self.make_button(inst_btns, "🗑  Удалить выбранный", RED,
                         self.on_delete, width=20).pack(side="left")
        self.make_button(inst_btns, "🔄  Обновить список", GRAY_BTN,
                         self._refresh_installed, width=16).pack(side="left", padx=8)
        self.label_installed_count = tk.Label(inst_btns, text="", font=("Arial", 9),
                                              bg=BG_DARK, fg=TEXT_DIM)
        self.label_installed_count.pack(side="right")

        self.status = tk.Label(self.win, text="Готово", font=("Arial", 9),
                               bg=BG_DARK, fg=TEXT_DIM, anchor="w")
        self.status.pack(fill="x", padx=16, pady=(4, 10))

    def _set_placeholder(self, event=None):
        if not self.entry_search.get():
            self.entry_search.insert(0, "Поиск модов: JEI, Sodium, Create...")
            self.entry_search.config(fg=TEXT_DIM)

    def _clear_placeholder(self, event=None):
        if self.entry_search.get().startswith("Поиск модов"):
            self.entry_search.delete(0, "end")
            self.entry_search.config(fg=TEXT_MAIN)

    def _on_select_mod(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        index = self._iid_to_index.get(selection[0])
        if index is None or index >= len(self.results):
            return
        hit = self.results[index]
        title = clean_str(hit["title"], 60)
        self.label_mod_title.config(text=f"{title}   ·   {hit['downloads_str']} скачиваний   ·   {hit['source']}")

        chosen = self._version_choice.get(hit["pid_key"])
        self.label_version_choice.config(
            text=f"Версия мода: {chosen} (выбрана вручную)" if chosen else "")

        self.text_desc.config(state="normal")
        self.text_desc.delete("1.0", "end")
        self.text_desc.insert("1.0", clean_str(hit.get("desc_full") or "Описание недоступно.", 400))
        self.text_desc.config(state="disabled")

        icon_url = hit.get("icon_url") or ""
        icon = self._photo_ready.get(icon_url)
        if icon is not None:
            self.label_desc_icon.config(image=icon)
            self._desc_photo = icon

    def _set_status(self, text, color=TEXT_DIM):
        self.status.config(text=text, fg=color)

    def _loader_category(self) -> str | None:
        loader = self.app.combo_loader.get()
        if loader == "Fabric":
            return "fabric"
        if loader == "NeoForge":
            return "neoforge"
        return None

    def _auto_search(self):
        if self._loader_category() is not None:
            self.on_search()

    def _make_photo_from_file(self, path: str):
        """Создаёт PhotoImage. Вызывать ТОЛЬКО в главном потоке tkinter!"""
        try:
            if PIL_AVAILABLE:
                pil_img = Image.open(path).copy()
                pil_img.thumbnail((ICON_SIZE, ICON_SIZE))
                return ImageTk.PhotoImage(pil_img)
            img = tk.PhotoImage(file=path)
            side = max(img.width(), img.height())
            factor = max(1, side // ICON_SIZE)
            if factor > 1:
                img = img.subsample(factor, factor)
            return img
        except Exception:
            return None

    def _attach_icon(self, iid: str, url: str, path: str):
        photo = self._make_photo_from_file(path)
        if photo is None:
            return
        self._photo_ready[url] = photo
        try:
            self.tree.item(iid, image=photo)
        except Exception:
            pass

        index = self._iid_to_index.get(iid)
        if index is not None and index < len(self.results):
            if (self.results[index].get("icon_url") or "") == url:
                self.label_desc_icon.config(image=photo)
                self._desc_photo = photo

    def _load_icons_async(self):
        tasks = list(self._row_icons)

        def work():
            for iid, url in tasks:
                if url in self._photo_ready:
                    continue
                path = download_icon_to_cache(url)
                if path:
                    self.win.after(0, lambda i=iid, u=url, p=path: self._attach_icon(i, u, p))

        threading.Thread(target=work, daemon=True).start()

    def on_search(self):
        if self._loader_category() is None:
            messagebox.showwarning(
                "Нужен загрузчик",
                "Моды работают только с ядрами Fabric или NeoForge.\n"
                "Выбери ядро в главном окне и запусти игру хотя бы раз,"
                " чтобы ядро установилось."
            )
            return

        self._set_status("Ищем моды...", ACCENT_HOVER)
        query = self.entry_search.get().strip()
        if query.startswith("Поиск модов"):
            query = ""
        source = self.combo_source.get()
        mc_version = self.app.combo_version.get()
        loader_cat = self._loader_category()

        def work():
            try:
                if source == "Modrinth":
                    hits = modrinth_search(query, mc_version, loader_cat)
                    normalized = [{
                        "id": h.get("project_id"),
                        "title": h.get("title", "?"),
                        "author": h.get("author", "—"),
                        "downloads": h.get("downloads", 0),
                        "desc_full": h.get("description", ""),
                        "icon_url": h.get("icon_url") or "",
                        "source": "Modrinth",
                        "pid_key": h.get("project_id"),
                    } for h in hits]
                else:
                    hits = cf_search(query, mc_version, loader_cat)
                    normalized = [{
                        "id": h.get("id"),
                        "title": h.get("name", "?"),
                        "author": clean_str((h.get("authors") or [{}])[0].get("name", ""), 40),
                        "downloads": h.get("downloadCount", 0),
                        "desc_full": h.get("summary", ""),
                        "icon_url": (h.get("logo") or {}).get("thumbnailUrl") or "",
                        "source": "CurseForge",
                        "pid_key": f"cf:{h.get('id')}",
                    } for h in hits]
                self.win.after(0, lambda: self._fill_results(normalized))
            except Exception:
                err = traceback.format_exc()
                for line in err.splitlines():
                    self.app.msg_queue.put(("log", line))
                self.win.after(0, lambda: self._set_status(
                    "Ошибка поиска — смотри лог в главном окне", RED))

        threading.Thread(target=work, daemon=True).start()

    def _fill_results(self, normalized):
        self.results = normalized
        self.tree.delete(*self.tree.get_children())
        self._row_icons = []
        self._iid_to_index = {}

        for index, h in enumerate(normalized):
            title = clean_str(h["title"], 60)
            author = clean_str(h.get("author", ""), 40) or "—"
            downloads = f"{h.get('downloads', 0):,}".replace(",", " ")
            h["downloads_str"] = downloads
            desc = clean_str(h.get("desc_full", ""), 60)

            installed = h["pid_key"] in self.db if h["pid_key"] else False
            tag = "installed" if installed else "normal"
            display_title = ("✓  " + title) if installed else title

            insert_kwargs = {}
            icon_url = h.get("icon_url") or ""
            if icon_url and icon_url in self._photo_ready:
                insert_kwargs["image"] = self._photo_ready[icon_url]

            iid = self.tree.insert("", "end", text="",
                                   values=(display_title, author, downloads, desc),
                                   tags=(tag,), **insert_kwargs)
            self._iid_to_index[iid] = index
            if icon_url:
                self._row_icons.append((iid, icon_url))

        self._set_status(f"Найдено модов: {len(normalized)}   ·   зелёные строки уже установлены")
        self._load_icons_async()

    # ---------- выбор версии мода ----------
    def on_pick_version(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Выбери мод", "Сначала выбери мод в списке каталога.")
            return
        index = self._iid_to_index.get(selection[0])
        if index is None or index >= len(self.results):
            return
        hit = self.results[index]

        mc_version = self.app.combo_version.get()
        loader_cat = self._loader_category()
        if loader_cat is None:
            messagebox.showwarning("Нужен загрузчик",
                                   "Выбери ядро Fabric или NeoForge в главном окне.")
            return

        self._set_status("Загружаем список версий...", ACCENT_HOVER)

        def work():
            try:
                if hit["source"] == "Modrinth":
                    versions = modrinth_versions(hit["id"], mc_version, loader_cat)
                    entries = []
                    for v in versions:
                        label = (f"{v.get('version_number', '?')}   ·   "
                                 f"{(v.get('date_published') or '')[:10]}")
                        entries.append((label, v.get("version_number")))
                else:
                    files = cf_files(hit["id"])
                    entries = []
                    for f in files:
                        gv = f.get("gameVersions") or []
                        mark = "✓" if mc_version in gv else " "
                        label = (f"{mark} {clean_str(f.get('displayName') or f.get('fileName', '?'), 48)}   ·   "
                                 f"{clean_str(f.get('fileDate') or f.get('dateModified') or '', 10)}")
                        entries.append((label, f.get("id")))
                self.win.after(0, lambda: self._open_version_dialog(hit, entries))
            except Exception:
                err = traceback.format_exc()
                for line in err.splitlines():
                    self.app.msg_queue.put(("log", line))
                self.win.after(0, lambda: self._set_status(
                    "Не удалось получить список версий — смотри лог", RED))

        threading.Thread(target=work, daemon=True).start()

    def _open_version_dialog(self, hit, entries):
        if not entries:
            self._set_status("Для этой версии игры и ядра нет файлов мода.", RED)
            return
        self._set_status(f"Доступно версий: {len(entries)}")
        VersionPickDialog(self.win, entries, self._on_version_chosen(hit))

    def _on_version_chosen(self, hit):
        def apply(payload):
            self._version_choice[hit["pid_key"]] = payload
            self.label_version_choice.config(text=f"Версия мода: {payload} (выбрана вручную)")
            self._set_status("Версия выбрана — жми «Установить выбранный»", ACCENT_HOVER)
        return apply

    # ---------- установка ----------
    def on_install(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Выбери мод", "Сначала выбери мод в списке каталога.")
            return
        index = self._iid_to_index.get(selection[0])
        if index is None or index >= len(self.results):
            return
        hit = self.results[index]
        title = clean_str(hit["title"], 60)
        source = hit.get("source", "Modrinth")
        mc_version = self.app.combo_version.get()
        loader_cat = self._loader_category()
        force = self._version_choice.get(hit["pid_key"])

        self.btn_install.config(state="disabled", text="Устанавливаем...")
        self._set_status(f"Устанавливаем {title}...", ACCENT_HOVER)
        q = self.app.msg_queue
        q.put(("log", f"— Установка мода: {title} ({source}) —"))

        def work():
            try:
                if source == "Modrinth":
                    install_mod_recursive(
                        hit["id"], mc_version, loader_cat,
                        q, set(), dict(self.db), is_root=True,
                        force_version=force,
                    )
                else:
                    install_mod_recursive_cf(
                        hit["id"], mc_version,
                        q, set(), dict(self.db), is_root=True,
                        force_file_id=force,
                    )
                q.put(("log", f"Мод {title} установлен. Перезапусти игру."))
                self.win.after(0, lambda: self._finish_install(title))
            except Exception:
                err = traceback.format_exc()
                for line in err.splitlines():
                    q.put(("log", line))
                self.win.after(0, lambda: self._set_status(
                    "Ошибка установки — смотри лог в главном окне", RED))
                self.win.after(0, lambda: self.btn_install.config(
                    state="normal", text="⬇  Установить выбранный"))

        threading.Thread(target=work, daemon=True).start()

    def _finish_install(self, title):
        self.btn_install.config(state="normal", text="⬇  Установить выбранный")
        self._set_status(f"✓  {title} установлен (зависимости — в логе главного окна)", "#7bd88f")
        self._refresh_installed()
        self.on_search()

    def on_delete(self):
        selection = self.tree_installed.selection()
        if not selection:
            return
        filename = self.tree_installed.set(selection[0], "file")
        path = os.path.join(MODS_DIR, filename)
        if os.path.isfile(path):
            os.remove(path)
        self.db = {pid: f for pid, f in self.db.items() if f != filename}
        save_installed_db(self.db)
        self._refresh_installed()
        self.on_search()

    def _refresh_installed(self):
        self.tree_installed.delete(*self.tree_installed.get_children())
        self.db = load_installed_db()
        count = 0
        if os.path.isdir(MODS_DIR):
            for f in sorted(os.listdir(MODS_DIR)):
                if f.endswith(".jar"):
                    self.tree_installed.insert("", "end", values=(f,))
                    count += 1
        self.label_installed_count.config(text=f"Всего: {count}")


class LauncherApp(DarkThemeMixin):
    def __init__(self, root):
        self.root = root
        self.root.title("Kotlauncher")
        self.root.geometry("620x700")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_DARK)
        self.process = None
        self.msg_queue = queue.Queue()

        self.setup_dark_styles(self.root)
        self.apply_window_icon(self.root)
        self._build_ui()
        self._check_java_async()

    def _build_ui(self):
        title = tk.Label(self.root, text="Kotlauncher", font=("Arial", 24, "bold"),
                         bg=BG_DARK, fg=TEXT_MAIN)
        title.pack(pady=(16, 4))

        tk.Label(self.root, text="— простой способ играть в Minecraft —",
                 font=("Arial", 9), bg=BG_DARK, fg=TEXT_DIM).pack(pady=(0, 8))

        frame_user = tk.Frame(self.root, bg=BG_DARK)
        frame_user.pack(pady=3)
        tk.Label(frame_user, text="Ник:", font=("Arial", 11),
                 bg=BG_DARK, fg=TEXT_MAIN).pack(side="left", padx=(0, 8))
        self.entry_user = self.make_entry(frame_user, width=25)
        self.entry_user.insert(0, "Player")
        self.entry_user.pack(side="left", ipady=5)

        frame_ver = tk.Frame(self.root, bg=BG_DARK)
        frame_ver.pack(pady=6)
        tk.Label(frame_ver, text="Версия:", font=("Arial", 11),
                 bg=BG_DARK, fg=TEXT_MAIN).pack(side="left", padx=(0, 8))
        self.combo_version = ttk.Combobox(frame_ver, width=14, state="readonly",
                                          style="Dark.TCombobox", font=("Arial", 10))
        self.combo_version.pack(side="left")
        self._fill_versions(list(FALLBACK_VERSIONS))
        self.combo_version.bind("<<ComboboxSelected>>", lambda e: self._refresh_loader_versions())

        tk.Label(frame_ver, text="  Ядро:", font=("Arial", 11),
                 bg=BG_DARK, fg=TEXT_MAIN).pack(side="left", padx=(10, 8))
        self.combo_loader = ttk.Combobox(frame_ver, width=10, state="readonly",
                                         values=LOADERS, font=("Arial", 10),
                                         style="Dark.TCombobox")
        self.combo_loader.set("Vanilla")
        self.combo_loader.pack(side="left")
        self.combo_loader.bind("<<ComboboxSelected>>", lambda e: self._refresh_loader_versions())

        frame_lver = tk.Frame(self.root, bg=BG_DARK)
        frame_lver.pack(pady=3)
        tk.Label(frame_lver, text="Версия ядра:", font=("Arial", 10),
                 bg=BG_DARK, fg=TEXT_MAIN).pack(side="left", padx=(0, 8))
        self.combo_loader_version = ttk.Combobox(frame_lver, width=26, state="readonly",
                                                 values=["Latest"], font=("Arial", 10),
                                                 style="Dark.TCombobox")
        self.combo_loader_version.set("Latest")
        self.combo_loader_version.pack(side="left")
        tk.Label(frame_lver, text="Latest = самая свежая", font=("Arial", 8),
                 bg=BG_DARK, fg=TEXT_DIM).pack(side="left", padx=(8, 0))

        self.label_status = tk.Label(self.root, text="Проверяем Java...",
                                     font=("Arial", 10), bg=BG_DARK, fg=TEXT_DIM)
        self.label_status.pack(pady=6)

        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=540,
                                        mode="determinate",
                                        style="Dark.Horizontal.TProgressbar")
        self.progress.pack(pady=4)

        self.btn_launch = self.make_button(
            self.root, text="▶  ИГРАТЬ", bg=GREEN,
            command=self.on_launch, width=20, font_size=14,
            hover_color=GREEN_HOVER,
        )
        self.btn_launch.config(height=2, state="disabled", disabledforeground="#cccccc")
        self.btn_launch.pack(pady=10)

        buttons_row = tk.Frame(self.root, bg=BG_DARK)
        buttons_row.pack(pady=(0, 8))

        self.btn_mods = self.make_button(
            buttons_row, text="🧩  Моды", bg=PURPLE,
            command=self.open_mods_window, width=18,
        )
        self.btn_mods.pack(side="left", padx=4)

        self.btn_settings = self.make_button(
            buttons_row, text="⚙  Настройки", bg=GRAY_BTN,
            command=self.open_settings_window, width=18,
        )
        self.btn_settings.pack(side="left", padx=4)

        log_panel = tk.Frame(self.root, bg=BG_PANEL)
        log_panel.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.log = tk.Text(log_panel, height=9, font=("Consolas", 8),
                           bg="#14141b", fg="#d4d4d4",
                           relief="flat", borderwidth=0,
                           insertbackground=TEXT_MAIN)
        self.log.pack(fill="both", expand=True, padx=2, pady=2)
        self.log.tag_config("error", foreground="#f48771")

        self._load_versions_async()

    def open_mods_window(self):
        ModsWindow(self)

    def open_settings_window(self):
        SettingsWindow(self)

    def log_write(self, text, error=False):
        self.log.insert("end", text + "\n", "error" if error else None)
        self.log.see("end")

    def set_status(self, text, color=TEXT_DIM):
        self.label_status.config(text=text, fg=color)

    def poll_queue(self):
        try:
            while True:
                kind, data = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log_write(data, error=data.startswith(("ERROR", "❌", "Traceback", "  ")))
                elif kind == "status":
                    self.set_status(*data)
                elif kind == "progress":
                    current, total = data
                    if total:
                        self.progress["maximum"] = total
                        self.progress["value"] = current
                elif kind == "ready":
                    self.btn_launch.config(state="normal")
                elif kind == "error":
                    messagebox.showerror("Ошибка", data)
                elif kind == "versions":
                    self._fill_versions(data)
                elif kind == "loader_versions":
                    versions = ["Latest"] + data
                    self.combo_loader_version["values"] = versions
                    self.combo_loader_version.set("Latest")
                    if not data:
                        self.set_status("Список версий ядра недоступен — будет Latest", TEXT_DIM)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    # ---------- версии ядер ----------
    def _refresh_loader_versions(self):
        mc_version = self.combo_version.get() or DEFAULT_VERSION
        loader = self.combo_loader.get()
        self.combo_loader_version["values"] = ["Latest"]
        self.combo_loader_version.set("Latest")

        def work():
            q = self.msg_queue
            try:
                if loader == "Fabric":
                    versions = fetch_fabric_loader_versions(mc_version)
                elif loader == "NeoForge":
                    versions = fetch_neoforge_versions(mc_version)
                else:
                    versions = []
                if not versions and loader != "Vanilla":
                    q.put(("log", f"Список версий {loader} для {mc_version} пуст —"
                                  " проверь соединение с meta.fabricmc.net"
                                  " / maven.neoforged.net."))
                q.put(("loader_versions", versions))
            except Exception:
                err = traceback.format_exc()
                for line in err.splitlines()[-4:]:
                    q.put(("log", line))
                q.put(("loader_versions", []))

        threading.Thread(target=work, daemon=True).start()

    # ---------- Java ----------
    def _check_java_async(self):
        threading.Thread(target=self._check_java, daemon=True).start()
        self.root.after(100, self.poll_queue)

    def _check_java(self):
        try:
            java_cmd = CONFIG.get("java_path") or "java"
            res = subprocess.run(
                [java_cmd, "-version"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, timeout=10,
            )
            match = re.search(r'version "((?:1\.)?(\d+))', res.stderr)
            major = int(match.group(2)) if match else 0
            if major >= 17:
                first_line = res.stderr.strip().splitlines()[0]
                self.msg_queue.put(("log", f"Java: {first_line}"))
                self.msg_queue.put(("status", (f"Java {major} ✓ — можно играть", "#7bd88f")))
            else:
                self.msg_queue.put(("status", (f"Java {major} слишком старая — нужна 17+", RED)))
                self.msg_queue.put(("log", "ERROR: установи Java 17+ с adoptium.net"))
                return

            version = self.combo_version.get() or DEFAULT_VERSION
            version_dir = os.path.join(GAME_DIR, "versions", version)
            installed = os.path.isfile(os.path.join(version_dir, version + ".json"))
            if installed:
                self.msg_queue.put(("status", (f"Версия {version} установлена — готово к игре", "#7bd88f")))
            else:
                self.msg_queue.put(("status", (f"Версия {version} не установлена — нажми ИГРАТЬ", "#e8b23f")))
            self.msg_queue.put(("ready", None))
        except FileNotFoundError:
            self.msg_queue.put(("status", ("Java не найдена — установи с adoptium.net", RED)))

    def _fill_versions(self, versions):
        self.combo_version["values"] = versions
        if DEFAULT_VERSION in versions:
            self.combo_version.set(DEFAULT_VERSION)
        elif versions:
            self.combo_version.current(0)

    def _load_versions_async(self):
        def load():
            try:
                online = fetch_release_versions()
                self.msg_queue.put(("versions", online))
            except Exception:
                err = traceback.format_exc()
                self.msg_queue.put(("log", "Онлайн-список версий недоступен, работает запасной список."))
                for line in err.splitlines()[-3:]:
                    self.msg_queue.put(("log", line))

        threading.Thread(target=load, daemon=True).start()

    def _make_callback(self, q):
        def set_status(text):
            q.put(("log", f"  {text}"))

        def set_max(value):
            self.progress["maximum"] = max(value, 1)

        def set_progress(value):
            q.put(("progress", (value, max(self.progress["maximum"], 1))))

        return {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}

    def _install_loader(self, mc_version, loader, loader_version, q) -> str:
        if loader == "Vanilla":
            return mc_version

        callback = self._make_callback(q)
        chosen = loader_version if loader_version and loader_version != "Latest" else None

        if loader == "Fabric":
            prefix = "fabric-loader"
            existing = find_loader_version(mc_version, prefix)
            # Повторно используем установленное ядро, только если оно совпадает
            # с выбранной версией (или выбрана Latest)
            if existing and (chosen is None or f"-{chosen}-" in existing):
                q.put(("log", f"Ядро Fabric уже установлено: {existing}"))
                return existing
            q.put(("status", (f"Устанавливаем Fabric для {mc_version}...", "#e8b23f")))
            q.put(("log", f"Устанавливаем Fabric {chosen or 'Latest'} для {mc_version}..."))
            run_with_retries(
                lambda: self._run_loader_install("fabric", mc_version, callback, q, chosen),
                INSTALL_RETRIES, q, f"установка Fabric {mc_version}",
            )
            installed = find_loader_version(mc_version, prefix)
            if not installed:
                raise RuntimeError("Не удалось найти установленную версию Fabric")
            q.put(("log", f"Fabric установлен: {installed}"))
            return installed

        if loader == "NeoForge":
            prefix = "neoforge"
            existing = find_loader_version(mc_version, prefix)
            if existing and (chosen is None or chosen in existing):
                q.put(("log", f"Ядро NeoForge уже установлено: {existing}"))
                return existing
            q.put(("status", (f"Устанавливаем NeoForge для {mc_version}...", "#e8b23f")))
            q.put(("log", f"Устанавливаем NeoForge {chosen or 'Latest'} для {mc_version}..."))
            if chosen:
                q.put(("log", "  Примечание: библиотека ставит последнюю стабильную сборку"
                              " NeoForge для этой версии игры; конкретная сборка может"
                              " не поддерживаться старой версией библиотеки."))
            run_with_retries(
                lambda: self._run_loader_install("neoforge", mc_version, callback, q, chosen),
                INSTALL_RETRIES, q, f"установка NeoForge {mc_version}",
            )
            installed = find_loader_version(mc_version, prefix)
            if not installed:
                raise RuntimeError("Не удалось найти установленную версию NeoForge")
            q.put(("log", f"NeoForge установлен: {installed}"))
            return installed

        return mc_version

    def _run_loader_install(self, loader_id: str, mc_version: str, callback, q,
                            loader_version: str | None = None):
        """Ставит ядро: новый mod_loader API или старые модули библиотеки."""
        # Новый API (библиотека 8.x)
        try:
            loader_obj = mll.mod_loader.get_mod_loader(loader_id)
            if loader_version:
                try:
                    loader_obj.install(mc_version, GAME_DIR,
                                       callback=callback, loader_version=loader_version)
                    return
                except TypeError:
                    pass  # старый вид install() без параметра версии
            loader_obj.install(mc_version, GAME_DIR, callback=callback)
            return
        except AttributeError:
            pass  # старая библиотека — используем старые модули
        except Exception:
            raise

        if loader_id == "fabric":
            kwargs = {"callback": callback}
            if loader_version:
                kwargs["loader_version"] = loader_version
            try:
                mll.fabric.install_fabric(mc_version, GAME_DIR, **kwargs)
                return
            except TypeError:
                mll.fabric.install_fabric(mc_version, GAME_DIR, callback=callback)
                return
        elif loader_id == "neoforge":
            if not hasattr(mll, "neoforge"):
                raise RuntimeError(
                    "NeoForge недоступен в этой версии библиотеки.\n"
                    "Обнови её: pip install -U minecraft-launcher-lib"
                )
            mll.neoforge.install_neoforge(mc_version, GAME_DIR, callback=callback)
        else:
            raise RuntimeError(f"Неизвестный загрузчик: {loader_id}")

    def on_launch(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Уже запущено", "Игра уже запущена!")
            return

        self.btn_launch.config(state="disabled")
        self.set_status("Установка/запуск...", "#e8b23f")
        version = self.combo_version.get() or DEFAULT_VERSION
        loader = self.combo_loader.get()
        loader_version = self.combo_loader_version.get() or "Latest"
        username = self.entry_user.get().strip() or "Player"

        threading.Thread(
            target=self._install_and_launch,
            args=(version, loader, loader_version, username),
            daemon=True,
        ).start()

    def _install_and_launch(self, mc_version, loader, loader_version, username):
        q = self.msg_queue
        try:
            os.makedirs(GAME_DIR, exist_ok=True)

            version_dir = os.path.join(GAME_DIR, "versions", mc_version)
            if not os.path.isfile(os.path.join(version_dir, mc_version + ".json")):
                q.put(("status", (f"Скачиваем Minecraft {mc_version}...", "#e8b23f")))
                q.put(("log", f"Устанавливаем Minecraft {mc_version}..."))
                run_with_retries(
                    lambda: mll.install.install_minecraft_version(
                        mc_version, GAME_DIR, callback=self._make_callback(q)),
                    INSTALL_RETRIES, q, f"установка Minecraft {mc_version}",
                )
                q.put(("log", f"Установка {mc_version} завершена."))

            launch_version = self._install_loader(mc_version, loader, loader_version, q)

            ram = max(2, min(16, int(CONFIG.get("ram_gb", 4) or 4)))
            options = {
                "username": username,
                "uuid": get_offline_uuid(username),
                "accessToken": "offline",
                "gameDirectory": GAME_DIR,
                "jvm": [f"-Xmx{ram}G", "-Xms512M"],
            }
            if CONFIG.get("java_path"):
                options["executablePath"] = CONFIG["java_path"]

            command = mll.command.get_minecraft_command(launch_version, GAME_DIR, options)
            q.put(("log", f"🚀 Запускаем Minecraft {launch_version} (ник: {username}, RAM: {ram} ГБ)..."))
            q.put(("status", (f"Minecraft запущен (ник: {username})", "#7bd88f")))

            self.process = subprocess.Popen(
                command, cwd=GAME_DIR,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in self.process.stdout:
                q.put(("log", line.rstrip()))
            self.process.wait()
            q.put(("log", f"Игра завершилась с кодом {self.process.returncode}"))
            q.put(("status", ("Игра закрыта — можно запускать снова", TEXT_DIM)))
        except Exception:
            err = traceback.format_exc()
            for line in err.splitlines():
                q.put(("log", line))
            q.put(("error", "Произошла ошибка — смотри текст в окне лога."))
            q.put(("status", ("Ошибка — смотри лог ниже", RED)))
        finally:
            q.put(("ready", None))


if __name__ == "__main__":
    os.makedirs(GAME_DIR, exist_ok=True)
    generate_app_icon()   # рисуем icon.ico, если его ещё нет
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()
