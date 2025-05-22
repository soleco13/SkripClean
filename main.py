import shutil
import time
from pathlib import Path


def format_size(size):
    """Форматирует размер в читаемый вид."""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} ТБ"


def is_excluded(path, exclude_dirs):
    """Проверяет, нужно ли исключить папку."""
    return any(part in exclude_dirs for part in path.parts)



def delete_folder(folder_path):
    """Удаляет указанную папку."""
    try:
        if folder_path.is_symlink():
            print(f"Путь {folder_path} является ссылкой. Пропуск...")
            return False
        if folder_path.resolve() == folder_path.anchor:
            print("Удаление корневого каталога запрещено.")
            return False

        shutil.rmtree(folder_path)
        log_action(f"Удалена папка: {folder_path}")
        print(f"Папка {folder_path} успешно удалена.")
        return True
    except Exception as e:
        print(f"Ошибка при удалении {folder_path}: {e}")
        log_action(f"Ошибка удаления: {folder_path} — {e}")
        return False


def log_action(message):
    """Логирует действия."""
    with open("folder_cleaner.log", "a", encoding="utf-8") as log_file:
        timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
        log_file.write(f"{timestamp} {message}\n")