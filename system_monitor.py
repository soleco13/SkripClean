import os
import sys
import time
import psutil
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (QSystemTrayIcon, QMenu, QAction, 
                           QWidget, QVBoxLayout, QProgressBar,
                           QLabel, QPushButton, QMessageBox)
from PyQt5.QtGui import QIcon

class SystemMonitor(QThread):
    """Мониторинг системы в реальном времени"""
    
    # Сигналы для обновления UI
    disk_space_update = pyqtSignal(dict)  # Информация о дисках
    temp_files_update = pyqtSignal(dict)  # Информация о временных файлах
    alert = pyqtSignal(str, str)  # Тип предупреждения и сообщение
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.check_interval = 300  # 5 минут
        self.alert_threshold = 0.85  # 85% заполнения
        self.temp_size_threshold = 1024 * 1024 * 1024  # 1 GB
        
        # Пути для мониторинга
        self.temp_paths = [
            os.environ.get('TEMP'),
            os.environ.get('TMP'),
            os.path.join(os.environ.get('LOCALAPPDATA'), 'Temp'),
            os.path.join(os.environ.get('WINDIR'), 'Temp'),
        ]
        
        # Кэш браузеров
        self.browser_paths = [
            os.path.join(os.environ.get('LOCALAPPDATA'), 'Google\\Chrome\\User Data\\Default\\Cache'),
            os.path.join(os.environ.get('LOCALAPPDATA'), 'Microsoft\\Edge\\User Data\\Default\\Cache'),
            os.path.join(os.environ.get('LOCALAPPDATA'), 'Mozilla\\Firefox\\Profiles'),
        ]
        
        # История проверок
        self.last_check = {}
        self.alert_history = []
        
    def run(self):
        """Основной цикл мониторинга"""
        while self.running:
            try:
                # Проверяем диски
                disk_info = self.check_disk_space()
                self.disk_space_update.emit(disk_info)
                
                # Проверяем временные файлы
                temp_info = self.check_temp_files()
                self.temp_files_update.emit(temp_info)
                
                # Анализируем и отправляем предупреждения
                self.analyze_system_state(disk_info, temp_info)
                
                # Ждем следующей проверки
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"Ошибка мониторинга: {e}")
                time.sleep(60)  # Ждем минуту при ошибке
                
    def stop(self):
        """Останавливает мониторинг"""
        self.running = False
        
    def check_disk_space(self) -> Dict[str, Dict]:
        """Проверяет свободное место на дисках"""
        disk_info = {}
        
        for disk in psutil.disk_partitions():
            try:
                if 'fixed' in disk.opts:  # Только фиксированные диски
                    usage = psutil.disk_usage(disk.mountpoint)
                    disk_info[disk.mountpoint] = {
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free,
                        'percent': usage.percent
                    }
            except Exception:
                continue
                
        return disk_info
        
    def check_temp_files(self) -> Dict[str, Dict]:
        """Проверяет размер временных файлов"""
        temp_info = {
            'system_temp': self.get_folder_size(self.temp_paths),
            'browser_cache': self.get_folder_size(self.browser_paths),
            'recycle_bin': self.get_recycle_bin_size()
        }
        return temp_info
        
    def analyze_system_state(self, disk_info: Dict, temp_info: Dict):
        """Анализирует состояние системы и отправляет предупреждения"""
        current_time = datetime.now()
        
        # Проверяем диски
        for disk, info in disk_info.items():
            if info['percent'] >= self.alert_threshold * 100:
                # Проверяем, не отправляли ли мы недавно предупреждение для этого диска
                if disk not in self.last_check or \
                   (current_time - self.last_check[disk]).total_seconds() > 3600:  # Раз в час
                    message = (f"Диск {disk} заполнен на {info['percent']}%. "
                             f"Свободно: {self.format_size(info['free'])}")
                    self.alert.emit('disk_space', message)
                    self.last_check[disk] = current_time
                    
        # Проверяем временные файлы
        total_temp = sum(temp_info.values())
        if total_temp > self.temp_size_threshold:
            if 'temp_files' not in self.last_check or \
               (current_time - self.last_check['temp_files']).total_seconds() > 7200:  # Раз в 2 часа
                message = (f"Обнаружено {self.format_size(total_temp)} временных файлов. "
                         "Рекомендуется очистка.")
                self.alert.emit('temp_files', message)
                self.last_check['temp_files'] = current_time
                
    @staticmethod
    def get_folder_size(paths: List[str]) -> int:
        """Получает общий размер папок"""
        total_size = 0
        
        for path in paths:
            try:
                if os.path.exists(path):
                    if os.path.isfile(path):
                        total_size += os.path.getsize(path)
                    else:
                        for dirpath, dirnames, filenames in os.walk(path):
                            for f in filenames:
                                fp = os.path.join(dirpath, f)
                                try:
                                    total_size += os.path.getsize(fp)
                                except OSError:
                                    continue
            except Exception:
                continue
                
        return total_size
        
    @staticmethod
    def get_recycle_bin_size() -> int:
        """Получает размер корзины"""
        try:
            # Получаем размер корзины через shell
            import winreg
            recycler_path = None
            
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                              "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\BitBucket") as key:
                recycler_path = winreg.QueryValueEx(key, "Volume")[0]
                
            if recycler_path:
                return SystemMonitor.get_folder_size([recycler_path])
                
        except Exception:
            pass
            
        return 0
        
    @staticmethod
    def format_size(size: int) -> str:
        """Форматирует размер в байтах в человекочитаемый вид"""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} ПБ"

class SystemTrayIcon(QSystemTrayIcon):
    """Иконка в системном трее"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(QIcon("icon1.ico"))  # Используем основную иконку приложения
        self.setToolTip("SkripClean - Мониторинг системы")
        
        # Создаем контекстное меню
        self.menu = QMenu()
        
        # Действия меню
        show_action = QAction("Показать", self)
        show_action.triggered.connect(self.show_status)
        self.menu.addAction(show_action)
        
        clean_action = QAction("Очистить сейчас", self)
        clean_action.triggered.connect(self.clean_system)
        self.menu.addAction(clean_action)
        
        self.menu.addSeparator()
        
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.exit_app)
        self.menu.addAction(exit_action)
        
        self.setContextMenu(self.menu)
        
        # Создаем монитор
        self.monitor = SystemMonitor()
        self.monitor.disk_space_update.connect(self.handle_disk_update)
        self.monitor.temp_files_update.connect(self.handle_temp_update)
        self.monitor.alert.connect(self.handle_alert)
        self.monitor.start()
        
        # Состояние системы
        self.current_state = {
            'disks': {},
            'temp_files': {}
        }
        
    def handle_disk_update(self, disk_info: Dict):
        """Обрабатывает обновление информации о дисках"""
        self.current_state['disks'] = disk_info
        self.update_tooltip()
        
    def handle_temp_update(self, temp_info: Dict):
        """Обрабатывает обновление информации о временных файлах"""
        self.current_state['temp_files'] = temp_info
        self.update_tooltip()
        
    def handle_alert(self, alert_type: str, message: str):
        """Обрабатывает предупреждения"""
        if alert_type == 'disk_space':
            self.showMessage("Предупреждение о диске", 
                           message,
                           QSystemTrayIcon.Warning)
        elif alert_type == 'temp_files':
            self.showMessage("Временные файлы",
                           message,
                           QSystemTrayIcon.Information)
        
    def update_tooltip(self):
        """Обновляет подсказку при наведении на иконку"""
        tooltip = "SkripClean - Мониторинг системы\n\n"
        
        # Добавляем информацию о дисках
        for disk, info in self.current_state['disks'].items():
            tooltip += f"Диск {disk}:\n"
            tooltip += f"Занято: {info['percent']}%\n"
            tooltip += f"Свободно: {self.monitor.format_size(info['free'])}\n\n"
            
        # Добавляем информацию о временных файлах
        temp_info = self.current_state['temp_files']
        if temp_info:
            tooltip += "Временные файлы:\n"
            tooltip += f"Система: {self.monitor.format_size(temp_info.get('system_temp', 0))}\n"
            tooltip += f"Браузеры: {self.monitor.format_size(temp_info.get('browser_cache', 0))}\n"
            tooltip += f"Корзина: {self.monitor.format_size(temp_info.get('recycle_bin', 0))}\n"
            
        self.setToolTip(tooltip)
        
    def show_status(self):
        """Показывает окно состояния системы"""
        status_window = SystemStatusWindow(self.current_state)
        status_window.show()
        
    def clean_system(self):
        """Запускает очистку системы"""
        reply = QMessageBox.question(
            None,
            'Подтверждение',
            'Вы уверены, что хотите выполнить очистку системы?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Здесь можно добавить вызов функции очистки
            pass
        
    def exit_app(self):
        """Выход из приложения"""
        self.monitor.stop()
        self.hide()
        QApplication.quit()

class SystemStatusWindow(QWidget):
    """Окно состояния системы"""
    
    def __init__(self, state: Dict):
        super().__init__()
        self.state = state
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle("Состояние системы")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout()
        
        # Информация о дисках
        layout.addWidget(QLabel("Состояние дисков:"))
        for disk, info in self.state['disks'].items():
            disk_label = QLabel(f"Диск {disk}")
            layout.addWidget(disk_label)
            
            progress = QProgressBar()
            progress.setValue(info['percent'])
            progress.setFormat(f"{info['percent']}% занято")
            layout.addWidget(progress)
            
            free_label = QLabel(f"Свободно: {SystemMonitor.format_size(info['free'])}")
            layout.addWidget(free_label)
            
        layout.addWidget(QLabel("\nВременные файлы:"))
        temp_info = self.state['temp_files']
        if temp_info:
            system_temp = QLabel(f"Системные: {SystemMonitor.format_size(temp_info.get('system_temp', 0))}")
            browser_cache = QLabel(f"Браузеры: {SystemMonitor.format_size(temp_info.get('browser_cache', 0))}")
            recycle_bin = QLabel(f"Корзина: {SystemMonitor.format_size(temp_info.get('recycle_bin', 0))}")
            
            layout.addWidget(system_temp)
            layout.addWidget(browser_cache)
            layout.addWidget(recycle_bin)
            
        # Кнопка очистки
        clean_button = QPushButton("Очистить сейчас")
        clean_button.clicked.connect(self.clean_system)
        layout.addWidget(clean_button)
        
        self.setLayout(layout)
        
    def clean_system(self):
        """Запускает очистку системы"""
        reply = QMessageBox.question(
            self,
            'Подтверждение',
            'Вы уверены, что хотите выполнить очистку системы?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Здесь можно добавить вызов функции очистки
            pass 