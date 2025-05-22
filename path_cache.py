import os
import json
import time
import sys
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

class PathCache:
    def __init__(self, cache_ttl: int = 3600):
        """
        Initialize the path cache system.
        
        Args:
            cache_ttl (int): Cache time-to-live in seconds (default: 1 hour)
        """
        # Определяем путь к директории приложения
        if getattr(sys, 'frozen', False):
            # Если приложение упаковано в exe
            app_dir = Path(os.path.dirname(sys.executable))
        else:
            # Если запущено как скрипт
            app_dir = Path(os.path.dirname(os.path.abspath(__file__)))
            
        # Создаем директорию для кеша если её нет
        cache_dir = app_dir / 'cache'
        try:
            cache_dir.mkdir(exist_ok=True)
        except PermissionError:
            # Если нет прав на запись в директорию приложения, используем AppData
            cache_dir = Path(os.getenv('APPDATA')) / 'SkripClean' / 'cache'
            cache_dir.mkdir(parents=True, exist_ok=True)
            
        self.cache_file = str(cache_dir / 'path_cache.json')
        self.cache_ttl = cache_ttl
        self.cache: Dict[str, dict] = {}
        self.load_cache()

    def load_cache(self) -> None:
        """Load cache from file if it exists."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            else:
                self.cache = {}
        except (json.JSONDecodeError, IOError, PermissionError):
            print(f"Ошибка при загрузке кеша из {self.cache_file}")
            self.cache = {}

    def save_cache(self) -> None:
        """Save cache to file."""
        try:
            # Создаем директорию для кеша если её нет
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except (IOError, PermissionError) as e:
            print(f"Ошибка при сохранении кеша в {self.cache_file}: {e}")

    def get_cached_folders(self, root_path: str) -> Optional[List[dict]]:
        """
        Get cached folders for a given root path if cache is still valid.
        
        Args:
            root_path (str): Root path to get cached folders for
            
        Returns:
            Optional[List[dict]]: List of cached folders or None if cache is invalid
        """
        if root_path in self.cache:
            cache_data = self.cache[root_path]
            cache_time = cache_data.get('timestamp', 0)
            
            # Check if cache is still valid
            if time.time() - cache_time <= self.cache_ttl:
                return cache_data.get('folders', [])
        return None

    def cache_folders(self, root_path: str, folders: List[dict]) -> None:
        """
        Cache folders for a given root path.
        
        Args:
            root_path (str): Root path to cache folders for
            folders (List[dict]): List of folder data to cache
        """
        self.cache[root_path] = {
            'timestamp': time.time(),
            'folders': folders
        }
        self.save_cache()

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.cache = {}
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
            except OSError:
                pass

    def is_cache_valid(self, root_path: str) -> bool:
        """
        Check if cache for given root path is valid.
        
        Args:
            root_path (str): Root path to check cache for
            
        Returns:
            bool: True if cache is valid, False otherwise
        """
        if root_path in self.cache:
            cache_time = self.cache[root_path].get('timestamp', 0)
            return time.time() - cache_time <= self.cache_ttl
        return False
