import os
import shutil
import winreg
import json
import logging
import threading
import time
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil
import win32com.client
import win32api
import win32file
import browser_cookie3
import send2trash
from datetime import datetime, timedelta


class CleaningMode(Enum):
    """Режимы очистки"""
    SAFE = "safe"  # Только безопасные временные файлы
    STANDARD = "standard"  # Стандартная очистка
    AGGRESSIVE = "aggressive"  # Агрессивная очистка (с предупреждениями)


class FileType(Enum):
    """Типы файлов для очистки"""
    TEMP = "temp"
    CACHE = "cache"
    LOGS = "logs"
    DOWNLOADS = "downloads"
    COOKIES = "cookies"
    HISTORY = "history"
    THUMBNAILS = "thumbnails"


@dataclass
class CleaningRule:
    """Правило очистки файлов"""
    path_patterns: List[str]
    file_extensions: Set[str] = field(default_factory=set)
    min_age_days: int = 7
    max_size_mb: Optional[int] = None
    exclude_patterns: List[str] = field(default_factory=list)
    file_type: FileType = FileType.TEMP
    enabled: bool = True


@dataclass
class CleaningResult:
    """Результат очистки"""
    files_removed: int = 0
    size_freed: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration: float = 0.0
    details: List[Dict] = field(default_factory=list)  # Добавляем поле для деталей


class SafetyChecker:
    """Класс для проверки безопасности операций"""

    CRITICAL_SYSTEM_PATHS = {
        r'C:\Windows\System32',
        r'C:\Windows\SysWOW64',
        r'C:\Windows\Boot',
        r'C:\Program Files',
        r'C:\Program Files (x86)',
        r'C:\ProgramData',
        r'C:\Recovery',
        r'C:\System Volume Information',
        r'C:\$Recycle.Bin'
    }

    CRITICAL_FILES = {
        'ntldr', 'bootmgr', 'pagefile.sys', 'hiberfil.sys',
        'ntuser.dat', 'system.dat', 'software.dat', 'default.dat',
        'boot.ini', 'bootstat.dat'
    }

    SAFE_EXTENSIONS = {
        '.tmp', '.temp', '.log', '.old', '.bak', '.cache',
        '.dmp', '.chk', '.gid', '.fts', '.ftg', '.ffa'
    }

    @classmethod
    def is_safe_to_delete(cls, file_path: str, mode: CleaningMode) -> Tuple[bool, str]:
        """Проверяет безопасность удаления файла"""
        path = Path(file_path)

        # Проверка критических системных путей
        for critical_path in cls.CRITICAL_SYSTEM_PATHS:
            if str(path).lower().startswith(critical_path.lower()):
                return False, f"Находится в критическом системном пути: {critical_path}"

        # Проверка критических файлов
        if path.name.lower() in cls.CRITICAL_FILES:
            return False, f"Критический системный файл: {path.name}"

        # Проверка расширений
        if mode == CleaningMode.SAFE and path.suffix.lower() not in cls.SAFE_EXTENSIONS:
            return False, f"Небезопасное расширение для SAFE режима: {path.suffix}"

        # Проверка использования файла
        if cls._is_file_in_use(file_path):
            return False, "Файл используется другим процессом"

        return True, ""

    @staticmethod
    def _is_file_in_use(file_path: str) -> bool:
        """Проверяет, используется ли файл"""
        try:
            # Попытка открыть файл в эксклюзивном режиме
            handle = win32file.CreateFile(
                file_path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,  # Не разрешаем совместное использование
                None,
                win32file.OPEN_EXISTING,
                0,
                None
            )
            win32file.CloseHandle(handle)
            return False
        except:
            return True


class SystemCleaner:
    """Улучшенный очиститель системы"""

    def __init__(self, mode: CleaningMode = CleaningMode.STANDARD):
        self.mode = mode
        self.safety_checker = SafetyChecker()
        self.setup_logging()
        self.load_cleaning_rules()
        self._setup_callbacks()
        self._running = False
        self._progress_callback: Optional[Callable[[str, int], None]] = None

    def setup_logging(self):
        """Настройка логирования"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f"cleaner_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('SystemCleaner')

    def load_cleaning_rules(self):
        """Загрузка правил очистки"""
        self.cleaning_rules = {
            'windows_temp': CleaningRule(
                path_patterns=[
                    os.environ.get('TEMP', ''),
                    os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Temp'),
                    r'C:\Windows\Temp',
                    r'C:\Windows\SoftwareDistribution\Download',
                    r'C:\Windows\Prefetch'
                ],
                file_extensions={'.tmp', '.temp', '.log', '.old', '.pf', '.etl', '.db', '.edb'},
                min_age_days=1 if self.mode == CleaningMode.AGGRESSIVE else 7,
                file_type=FileType.TEMP
            ),

            'user_temp': CleaningRule(
                path_patterns=[
                    os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Temp'),
                    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Temp')
                ],
                file_extensions={'.tmp', '.temp', '.log', '.~*', '.bak', '.old'},
                min_age_days=3,
                file_type=FileType.TEMP
            ),

            'browser_cache': CleaningRule(
                path_patterns=[
                    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default',
                                 'Cache'),
                    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'User Data', 'Default',
                                 'Cache'),
                    os.path.join(os.environ.get('APPDATA', ''), 'Mozilla', 'Firefox', 'Profiles')
                ],
                min_age_days=7,
                max_size_mb=1000,  # Не удалять файлы кэша больше 1GB
                file_type=FileType.CACHE
            ),

            'system_logs': CleaningRule(
                path_patterns=[
                    r'C:\Windows\Logs',
                    r'C:\Windows\Debug',
                    os.path.join(os.environ.get('WINDIR', ''), 'Panther')
                ],
                file_extensions={'.log', '.txt', '.etl', '.evtx'},
                min_age_days=30,
                file_type=FileType.LOGS,
                enabled=self.mode != CleaningMode.SAFE
            ),

            'thumbnails': CleaningRule(
                path_patterns=[
                    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Explorer')
                ],
                file_extensions={'.db'},
                min_age_days=14,
                file_type=FileType.THUMBNAILS
            )
        }

    def _setup_callbacks(self):
        """Настройка колбэков для прогресса"""
        self._progress_callback = None

    def set_progress_callback(self, callback: Callable[[str, int], None]):
        """Установка колбэка для отслеживания прогресса"""
        self._progress_callback = callback

    def _update_progress(self, message: str, percentage: int):
        """Обновление прогресса"""
        if self._progress_callback:
            self._progress_callback(message, percentage)

    @staticmethod
    def get_size_format(bytes_size: int) -> str:
        """Форматирование размера в человекочитаемый вид"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"

    def _get_file_age_days(self, file_path: str) -> int:
        """Получение возраста файла в днях"""
        try:
            mtime = os.path.getmtime(file_path)
            age = datetime.now() - datetime.fromtimestamp(mtime)
            return age.days
        except OSError:
            return 0

    def _should_clean_file(self, file_path: str, rule: CleaningRule) -> Tuple[bool, str]:
        """Проверка, нужно ли очищать файл согласно правилу"""
        path = Path(file_path)

        # Проверка расширения
        if rule.file_extensions and path.suffix.lower() not in rule.file_extensions:
            return False, "Расширение не соответствует правилу"

        # Проверка возраста
        if self._get_file_age_days(file_path) < rule.min_age_days:
            return False, f"Файл слишком новый (младше {rule.min_age_days} дней)"

        # Проверка размера
        if rule.max_size_mb:
            try:
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if size_mb > rule.max_size_mb:
                    return False, f"Файл слишком большой ({size_mb:.1f}MB > {rule.max_size_mb}MB)"
            except OSError:
                return False, "Ошибка получения размера файла"

        # Проверка исключений
        for exclude_pattern in rule.exclude_patterns:
            if exclude_pattern.lower() in str(path).lower():
                return False, f"Файл исключен по паттерну: {exclude_pattern}"

        # Проверка безопасности
        is_safe, reason = self.safety_checker.is_safe_to_delete(file_path, self.mode)
        if not is_safe:
            return False, reason

        return True, ""

    def _clean_path(self, path: str, rule: CleaningRule) -> CleaningResult:
        """Очистка конкретного пути согласно правилу"""
        result = CleaningResult()
        start_time = time.time()

        if not os.path.exists(path):
            result.warnings.append(f"Путь не существует: {path}")
            return result

        try:
            if os.path.isfile(path):
                should_clean, reason = self._should_clean_file(path, rule)
                if should_clean:
                    size = os.path.getsize(path)
                    send2trash.send2trash(path)
                    result.files_removed += 1
                    result.size_freed += size
                    self.logger.info(f"Удален файл: {path} ({self.get_size_format(size)})")
                else:
                    self.logger.debug(f"Пропущен файл {path}: {reason}")

            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path, topdown=False):
                    # Очистка файлов
                    for file in files:
                        if not self._running:
                            break

                        file_path = os.path.join(root, file)
                        should_clean, reason = self._should_clean_file(file_path, rule)

                        if should_clean:
                            try:
                                size = os.path.getsize(file_path)
                                send2trash.send2trash(file_path)
                                result.files_removed += 1
                                result.size_freed += size
                                self.logger.info(f"Удален файл: {file_path}")
                            except Exception as e:
                                error_msg = f"Ошибка удаления {file_path}: {str(e)}"
                                result.errors.append(error_msg)
                                self.logger.error(error_msg)
                        else:
                            self.logger.debug(f"Пропущен файл {file_path}: {reason}")

                    # Удаление пустых директорий
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        try:
                            if not os.listdir(dir_path):  # Если директория пуста
                                os.rmdir(dir_path)
                                self.logger.info(f"Удалена пустая директория: {dir_path}")
                        except Exception as e:
                            self.logger.debug(f"Не удалось удалить директорию {dir_path}: {str(e)}")

        except Exception as e:
            error_msg = f"Критическая ошибка при очистке {path}: {str(e)}"
            result.errors.append(error_msg)
            self.logger.error(error_msg)

        result.duration = time.time() - start_time
        return result

    def clean_recycle_bin(self) -> CleaningResult:
        """Очистка корзины"""
        result = CleaningResult()
        start_time = time.time()

        try:
            shell = win32com.client.Dispatch("Shell.Application")
            recycle_bin = shell.Namespace(10)  # CSIDL_BITBUCKET
            items = recycle_bin.Items()

            total_size = 0
            item_count = 0

            for item in items:
                try:
                    total_size += item.Size
                    item_count += 1
                except:
                    pass

            if item_count > 0:
                # Очистка корзины
                recycle_bin.Items().InvokeVerbEx("delete")
                result.files_removed = item_count
                result.size_freed = total_size
                self.logger.info(f"Очищена корзина: {item_count} элементов, {self.get_size_format(total_size)}")
            else:
                self.logger.info("Корзина уже пуста")

        except Exception as e:
            error_msg = f"Ошибка при очистке корзины: {str(e)}"
            result.errors.append(error_msg)
            self.logger.error(error_msg)

        result.duration = time.time() - start_time
        return result

    def clean_browser_data(self) -> CleaningResult:
        """Специализированная очистка данных браузеров"""
        result = CleaningResult()
        start_time = time.time()

        browsers = {
            'Chrome': {
                'path': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default'),
                'cache_dirs': ['Cache', 'Code Cache', 'GPUCache'],
                'cookie_func': browser_cookie3.chrome
            },
            'Edge': {
                'path': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'User Data', 'Default'),
                'cache_dirs': ['Cache', 'Code Cache', 'GPUCache'],
                'cookie_func': browser_cookie3.edge
            },
            'Firefox': {
                'path': os.path.join(os.environ.get('APPDATA', ''), 'Mozilla', 'Firefox', 'Profiles'),
                'cache_dirs': ['cache2'],
                'cookie_func': browser_cookie3.firefox
            }
        }

        for browser_name, config in browsers.items():
            if not os.path.exists(config['path']):
                continue

            self.logger.info(f"Очистка данных {browser_name}")

            # Очистка кэша
            for cache_dir in config['cache_dirs']:
                cache_path = os.path.join(config['path'], cache_dir)
                if os.path.exists(cache_path):
                    try:
                        size_before = self._get_directory_size(cache_path)
                        shutil.rmtree(cache_path, ignore_errors=True)
                        result.size_freed += size_before
                        result.files_removed += 1
                        self.logger.info(f"Очищен кэш {browser_name}/{cache_dir}")
                    except Exception as e:
                        result.errors.append(f"Ошибка очистки кэша {browser_name}: {str(e)}")

            # Очистка истории (только для агрессивного режима)
            if self.mode == CleaningMode.AGGRESSIVE:
                history_file = os.path.join(config['path'], 'History')
                if os.path.exists(history_file):
                    try:
                        size = os.path.getsize(history_file)
                        send2trash.send2trash(history_file)
                        result.size_freed += size
                        result.files_removed += 1
                        self.logger.info(f"Очищена история {browser_name}")
                    except Exception as e:
                        result.errors.append(f"Ошибка очистки истории {browser_name}: {str(e)}")

        result.duration = time.time() - start_time
        return result

    def _get_directory_size(self, path: str) -> int:
        """Получение размера директории"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(file_path)
                    except OSError:
                        continue
        except OSError:
            pass
        return total_size

    def get_cleaning_preview(self) -> Dict[str, CleaningResult]:
        """Предварительный просмотр файлов для очистки (без фактического удаления)"""
        preview_results = {}

        for rule_name, rule in self.cleaning_rules.items():
            if not rule.enabled:
                continue

            preview_results[rule_name] = CleaningResult()

            for path_pattern in rule.path_patterns:
                if not path_pattern or not os.path.exists(path_pattern):
                    continue

                if os.path.isfile(path_pattern):
                    should_clean, reason = self._should_clean_file(path_pattern, rule)
                    if should_clean:
                        try:
                            size = os.path.getsize(path_pattern)
                            preview_results[rule_name].files_removed += 1
                            preview_results[rule_name].size_freed += size
                            preview_results[rule_name].details.append({
                                'path': path_pattern,
                                'size': size,
                                'type': 'file'
                            })
                        except OSError:
                            pass

                elif os.path.isdir(path_pattern):
                    for root, dirs, files in os.walk(path_pattern):
                        for file in files:
                            file_path = os.path.join(root, file)
                            should_clean, reason = self._should_clean_file(file_path, rule)
                            if should_clean:
                                try:
                                    size = os.path.getsize(file_path)
                                    preview_results[rule_name].files_removed += 1
                                    preview_results[rule_name].size_freed += size
                                    preview_results[rule_name].details.append({
                                        'path': file_path,
                                        'size': size,
                                        'type': 'file'
                                    })
                                except OSError:
                                    continue

        # Добавляем предварительный просмотр корзины
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            recycle_bin = shell.Namespace(10)
            items = recycle_bin.Items()
            
            recycle_result = CleaningResult()
            for item in items:
                try:
                    size = item.Size
                    recycle_result.files_removed += 1
                    recycle_result.size_freed += size
                    recycle_result.details.append({
                        'path': item.Name,
                        'size': size,
                        'type': 'recycle_bin'
                    })
                except:
                    continue
            
            if recycle_result.files_removed > 0:
                preview_results['recycle_bin'] = recycle_result
                
        except Exception as e:
            self.logger.error(f"Ошибка при анализе корзины: {str(e)}")

        # Добавляем предварительный просмотр браузеров
        browsers = {
            'Chrome': {
                'path': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default'),
                'cache_dirs': ['Cache', 'Code Cache', 'GPUCache']
            },
            'Edge': {
                'path': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'User Data', 'Default'),
                'cache_dirs': ['Cache', 'Code Cache', 'GPUCache']
            },
            'Firefox': {
                'path': os.path.join(os.environ.get('APPDATA', ''), 'Mozilla', 'Firefox', 'Profiles'),
                'cache_dirs': ['cache2']
            }
        }

        browser_result = CleaningResult()
        for browser_name, config in browsers.items():
            if not os.path.exists(config['path']):
                continue

            for cache_dir in config['cache_dirs']:
                cache_path = os.path.join(config['path'], cache_dir)
                if os.path.exists(cache_path):
                    try:
                        size = self._get_directory_size(cache_path)
                        if size > 0:
                            browser_result.files_removed += 1
                            browser_result.size_freed += size
                            browser_result.details.append({
                                'path': f"{browser_name} - {cache_dir}",
                                'size': size,
                                'type': 'browser_cache'
                            })
                    except Exception as e:
                        self.logger.error(f"Ошибка при анализе кэша {browser_name}: {str(e)}")

        if browser_result.files_removed > 0:
            preview_results['browser_data'] = browser_result

        return preview_results

    def clean_system(self, include_recycle_bin: bool = True,
                     include_browser_data: bool = True,
                     selected_categories: List[str] = None,
                     cleaning_mode: CleaningMode = None) -> Dict[str, CleaningResult]:
        """Полная очистка системы"""
        if cleaning_mode is not None:
            self.mode = cleaning_mode
        
        self._running = True
        start_time = time.time()
        results = {}

        try:
            self.logger.info(f"Начало очистки системы в режиме {self.mode.value}")
            self._update_progress("Инициализация очистки...", 0)

            # Фильтруем правила очистки по выбранным категориям
            enabled_rules = {}
            if selected_categories:
                for rule_name, rule in self.cleaning_rules.items():
                    if rule_name in selected_categories:
                        enabled_rules[rule_name] = rule
            else:
                enabled_rules = {name: rule for name, rule in self.cleaning_rules.items() if rule.enabled}

            # Обновляем правила в соответствии с режимом
            for rule in enabled_rules.values():
                if self.mode == CleaningMode.SAFE:
                    rule.min_age_days = max(rule.min_age_days, 7)  # Минимум 7 дней для безопасного режима
                elif self.mode == CleaningMode.AGGRESSIVE:
                    rule.min_age_days = 1  # 1 день для агрессивного режима

            total_steps = len(enabled_rules)
            if include_recycle_bin and ('recycle_bin' in selected_categories if selected_categories else True):
                total_steps += 1
            if include_browser_data and ('browser_data' in selected_categories if selected_categories else True):
                total_steps += 1

            current_step = 0

            # Очистка по правилам
            for rule_name, rule in enabled_rules.items():
                if not self._running:
                    break

                self._update_progress(f"Очистка {rule_name}...",
                                      int((current_step / total_steps) * 100))

                rule_result = CleaningResult()

                for path_pattern in rule.path_patterns:
                    if not self._running:
                        break
                    path_result = self._clean_path(path_pattern, rule)
                    rule_result.files_removed += path_result.files_removed
                    rule_result.size_freed += path_result.size_freed
                    rule_result.errors.extend(path_result.errors)
                    rule_result.warnings.extend(path_result.warnings)
                    rule_result.duration += path_result.duration

                results[rule_name] = rule_result
                current_step += 1

            # Очистка корзины
            if include_recycle_bin and ('recycle_bin' in selected_categories if selected_categories else True) and self._running:
                self._update_progress("Очистка корзины...",
                                      int((current_step / total_steps) * 100))
                results['recycle_bin'] = self.clean_recycle_bin()
                current_step += 1

            # Очистка данных браузеров
            if include_browser_data and ('browser_data' in selected_categories if selected_categories else True) and self._running:
                self._update_progress("Очистка данных браузеров...",
                                      int((current_step / total_steps) * 100))
                results['browser_data'] = self.clean_browser_data()
                current_step += 1

            self._update_progress("Очистка завершена", 100)

            # Сводная статистика
            total_files = sum(r.files_removed for r in results.values())
            total_size = sum(r.size_freed for r in results.values())
            total_duration = time.time() - start_time

            self.logger.info(f"Очистка завершена за {total_duration:.1f}с")
            self.logger.info(f"Удалено файлов: {total_files}")
            self.logger.info(f"Освобождено места: {self.get_size_format(total_size)}")

        except KeyboardInterrupt:
            self.logger.info("Очистка прервана пользователем")
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {str(e)}")
        finally:
            self._running = False

        return results

    def stop_cleaning(self):
        """Остановка процесса очистки"""
        self._running = False
        self.logger.info("Запрос на остановку очистки")

    def export_results(self, results: Dict[str, CleaningResult],
                       file_path: str = None) -> str:
        """Экспорт результатов в JSON файл"""
        if not file_path:
            file_path = f"cleaning_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        export_data = {
            'timestamp': datetime.now().isoformat(),
            'mode': self.mode.value,
            'results': {}
        }

        for category, result in results.items():
            export_data['results'][category] = {
                'files_removed': result.files_removed,
                'size_freed': result.size_freed,
                'size_freed_formatted': self.get_size_format(result.size_freed),
                'duration': result.duration,
                'errors': result.errors,
                'warnings': result.warnings
            }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        return file_path


def main():
    """Основная функция для тестирования"""
    try:
        # Создание очистителя в безопасном режиме
        cleaner = SystemCleaner(CleaningMode.SAFE)

        # Установка колбэка для прогресса
        def progress_callback(message: str, percentage: int):
            print(f"[{percentage:3d}%] {message}")

        cleaner.set_progress_callback(progress_callback)

        # Предварительный просмотр
        print("=== ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР ===")
        preview = cleaner.get_cleaning_preview()

        total_files = sum(r.files_removed for r in preview.values())
        total_size = sum(r.size_freed for r in preview.values())

        print(f"Будет удалено файлов: {total_files}")
        print(f"Будет освобождено места: {cleaner.get_size_format(total_size)}")

        for category, result in preview.items():
            if result.files_removed > 0:
                print(f"  {category}: {result.files_removed} файлов, "
                      f"{cleaner.get_size_format(result.size_freed)}")

        # Подтверждение пользователя
        response = input("\nПродолжить очистку? (y/N): ")
        if response.lower() != 'y':
            print("Очистка отменена")
            return

        # Запуск очистки
        print("\n=== ЗАПУСК ОЧИСТКИ ===")
        results = cleaner.clean_system()

        # Экспорт результатов
        report_file = cleaner.export_results(results)
        print(f"\nОтчет сохранен в: {report_file}")

    except KeyboardInterrupt:
        print("\nОчистка прервана пользователем")
    except Exception as e:
        print(f"Ошибка: {str(e)}")


if __name__ == "__main__":
    main()