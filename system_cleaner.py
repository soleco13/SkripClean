import os
import shutil
import winreg
import json
import logging
from pathlib import Path
import psutil
import win32com.client
from typing import List, Dict, Set
import browser_cookie3
import send2trash
import sys
from datetime import datetime, timedelta

class SystemCleaner:
    def __init__(self):
        self.temp_paths = {
            'windows_temp': os.environ.get('TEMP'),
            'system_temp': r'C:\Windows\Temp',
            'prefetch': r'C:\Windows\Prefetch',
            'recent': os.path.join(os.environ['USERPROFILE'], 'Recent')
        }
        
        self.browser_paths = {
            'chrome': os.path.join(os.environ['LOCALAPPDATA'], 'Google\\Chrome\\User Data\\Default'),
            'firefox': os.path.join(os.environ['APPDATA'], 'Mozilla\\Firefox\\Profiles'),
            'edge': os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft\\Edge\\User Data\\Default')
        }

        # Защищенные пути, которые нельзя удалять
        self.protected_paths = {
            os.environ['WINDIR'],  # Windows
            os.environ['PROGRAMFILES'],  # Program Files
            os.environ['PROGRAMFILES(X86)'],  # Program Files (x86)
            os.environ['PROGRAMDATA'],  # ProgramData
            os.environ['SYSTEMROOT'],  # System32
            os.path.join(os.environ['SYSTEMDRIVE'], 'Recovery'),  # Recovery
            os.path.join(os.environ['SYSTEMDRIVE'], 'System Volume Information'),
            os.environ.get('USERPROFILE'),  # Профиль пользователя
        }

        # Защищенные расширения файлов
        self.protected_extensions = {
            '.exe', '.dll', '.sys', '.ini', '.dat', '.key',
            '.doc', '.docx', '.xls', '.xlsx', '.pdf', '.ppt', '.pptx',
            '.jpg', '.jpeg', '.png', '.gif', '.mp3', '.mp4', '.avi',
            '.zip', '.rar', '.7z', '.iso',
            '.db', '.mdb', '.accdb', '.sql', '.sqlite'
        }

        # Защищенные имена файлов и папок
        self.protected_names = {
            'desktop.ini', 'thumbs.db', 'pagefile.sys', 'hiberfil.sys',
            'ntuser.dat', 'ntuser.ini', 'boot', 'system32', 'drivers',
            'config', 'windows', 'program files', 'program files (x86)',
            'programdata', 'appdata', 'local', 'roaming'
        }

        # Минимальный возраст файлов для удаления (в днях)
        self.min_file_age = {
            'temp': 7,  # Временные файлы старше 7 дней
            'cache': 14,  # Кэш старше 14 дней
            'logs': 30,  # Логи старше 30 дней
            'downloads': 90  # Загрузки старше 90 дней
        }
        
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            filename='system_cleaner.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('SystemCleaner')

    def get_size_format(self, bytes: int) -> str:
        """Конвертирует байты в читаемый формат"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024.0:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024.0

    def is_protected_path(self, path: str) -> bool:
        """Проверяет, является ли путь защищенным"""
        path_lower = path.lower()
        
        # Проверка защищенных путей
        for protected in self.protected_paths:
            if protected and path_lower.startswith(protected.lower()):
                return True

        # Проверка защищенных имен
        path_parts = Path(path_lower).parts
        if any(name.lower() in self.protected_names for name in path_parts):
            return True

        return False

    def is_protected_file(self, path: str) -> bool:
        """Проверяет, является ли файл защищенным"""
        file_path = Path(path)
        
        # Проверка расширения
        if file_path.suffix.lower() in self.protected_extensions:
            return True

        # Проверка имени файла
        if file_path.name.lower() in self.protected_names:
            return True

        # Проверка размера файла (не удалять файлы больше 100МБ)
        try:
            if os.path.getsize(path) > 100 * 1024 * 1024:
                return True
        except OSError:
            return True

        return False

    def is_file_old_enough(self, path: str, file_type: str) -> bool:
        """Проверяет, достаточно ли старый файл для удаления"""
        try:
            mtime = os.path.getmtime(path)
            file_age = datetime.now() - datetime.fromtimestamp(mtime)
            min_age = self.min_file_age.get(file_type, 7)  # По умолчанию 7 дней
            return file_age.days >= min_age
        except OSError:
            return False

    def is_system_file_in_use(self, path: str) -> bool:
        """Проверяет, используется ли системный файл"""
        try:
            # Пытаемся открыть файл для записи
            with open(path, 'ab') as f:
                return False
        except:
            return True

    def safe_remove(self, path: str, file_type: str = 'temp') -> None:
        """Безопасное удаление файла или директории с проверками"""
        try:
            # Проверка базовых условий
            if self.is_protected_path(path):
                self.logger.warning(f"Попытка удаления защищенного пути: {path}")
                return

            if os.path.isfile(path):
                if self.is_protected_file(path):
                    self.logger.warning(f"Попытка удаления защищенного файла: {path}")
                    return

                if not self.is_file_old_enough(path, file_type):
                    self.logger.info(f"Файл слишком новый для удаления: {path}")
                    return

                if self.is_system_file_in_use(path):
                    self.logger.warning(f"Файл используется системой: {path}")
                    return

                # Безопасное удаление в корзину
                send2trash.send2trash(path)
                self.logger.info(f"Файл успешно удален: {path}")

            elif os.path.isdir(path):
                # Для директорий проверяем каждый файл
                empty = True
                for root, dirs, files in os.walk(path, topdown=False):
                    for name in files:
                        file_path = os.path.join(root, name)
                        if not self.is_protected_file(file_path) and \
                           self.is_file_old_enough(file_path, file_type) and \
                           not self.is_system_file_in_use(file_path):
                            try:
                                send2trash.send2trash(file_path)
                                self.logger.info(f"Файл успешно удален: {file_path}")
                            except Exception as e:
                                empty = False
                                self.logger.error(f"Ошибка при удалении файла {file_path}: {str(e)}")
                        else:
                            empty = False

                # Удаляем пустую директорию
                if empty and not self.is_protected_path(path):
                    try:
                        os.rmdir(path)
                        self.logger.info(f"Пустая директория удалена: {path}")
                    except Exception as e:
                        self.logger.error(f"Ошибка при удалении директории {path}: {str(e)}")

        except Exception as e:
            self.logger.error(f"Ошибка при удалении {path}: {str(e)}")

    def clean_windows_temp(self) -> Dict[str, int]:
        """Очистка временных файлов Windows"""
        cleaned_size = 0
        files_removed = 0
        
        for temp_type, temp_path in self.temp_paths.items():
            if os.path.exists(temp_path):
                for root, dirs, files in os.walk(temp_path):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            size = os.path.getsize(file_path)
                            self.safe_remove(file_path)
                            cleaned_size += size
                            files_removed += 1
                        except Exception as e:
                            self.logger.error(f"Ошибка при очистке {file_path}: {str(e)}")

        return {
            'cleaned_size': cleaned_size,
            'files_removed': files_removed
        }

    def clean_browsers(self) -> Dict[str, int]:
        """Очистка кэша и временных файлов браузеров"""
        cleaned_size = 0
        files_removed = 0

        for browser, path in self.browser_paths.items():
            if os.path.exists(path):
                # Очистка кэша
                cache_path = os.path.join(path, 'Cache')
                if os.path.exists(cache_path):
                    cleaned_size += self._get_dir_size(cache_path)
                    self.safe_remove(cache_path)
                    files_removed += 1

                # Очистка cookies
                try:
                    if browser == 'chrome':
                        cookies = browser_cookie3.chrome(domain_name='')
                    elif browser == 'firefox':
                        cookies = browser_cookie3.firefox(domain_name='')
                    elif browser == 'edge':
                        cookies = browser_cookie3.edge(domain_name='')
                        
                    for cookie in cookies:
                        cookie.expires = 0
                except Exception as e:
                    self.logger.error(f"Ошибка при очистке cookies {browser}: {str(e)}")

        return {
            'cleaned_size': cleaned_size,
            'files_removed': files_removed
        }

    def empty_recycle_bin(self) -> Dict[str, int]:
        """Очистка корзины"""
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            recycle_bin = shell.Namespace(10)
            items = recycle_bin.Items()
            size = sum(item.Size for item in items)
            items.Delete()
            return {
                'cleaned_size': size,
                'files_removed': len(items)
            }
        except Exception as e:
            self.logger.error(f"Ошибка при очистке корзины: {str(e)}")
            return {'cleaned_size': 0, 'files_removed': 0}

    def _get_dir_size(self, path: str) -> int:
        """Получение размера директории"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                except OSError:
                    continue
        return total_size

    def clean_system(self) -> Dict[str, Dict[str, int]]:
        """Запуск полной очистки системы"""
        results = {
            'windows_temp': self.clean_windows_temp(),
            'browsers': self.clean_browsers(),
            'recycle_bin': self.empty_recycle_bin()
        }

        total_cleaned = sum(r['cleaned_size'] for r in results.values())
        total_files = sum(r['files_removed'] for r in results.values())

        self.logger.info(f"Очистка завершена. Освобождено: {self.get_size_format(total_cleaned)}")
        self.logger.info(f"Всего удалено файлов: {total_files}")

        return results 