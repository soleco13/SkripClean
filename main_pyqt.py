import sys
import os
import shutil
import time
from pathlib import Path
from tqdm import tqdm
import threading

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFileDialog, QSpinBox, QProgressBar,
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                             QComboBox, QStyle, QStyledItemDelegate, QAbstractItemView,
                             QTabWidget, QDialog, QTreeWidget, QTreeWidgetItem, QGroupBox,
                             QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QSettings
from PyQt5.QtGui import QIcon, QColor, QFont, QPalette, QBrush, QLinearGradient

# Импортируем функции из main.py и C++ модуля
from main import format_size, is_excluded, delete_folder, log_action
import folder_search_cpp as fs_cpp
# Импортируем функции из ai_consultant.py
from ai_consultant import show_ai_assistant_dialog
# Импортируем систему кеширования
from path_cache import PathCache
# Импортируем функцию для добавления вкладки восстановления файлов
from autorun_manager import AutorunManager
# Импортируем диалог отказа от ответственности
from disclaimer_dialog import DisclaimerDialog
from system_cleaner import SystemCleaner
# Импортируем модуль управления программами
from program_uninstaller import ProgramUninstallerWidget


# Создаем глобальный экземпляр кеша
path_cache = PathCache()

# Стили и цвета
PRIMARY_COLOR = "#4a6fa5"
SECONDARY_COLOR = "#6b8cae"
ACCENT_COLOR = "#e63946"
BACKGROUND_COLOR = "#f8f9fa"
TEXT_COLOR = "#212529"

# Класс для выполнения сканирования в отдельном потоке
class ScanWorker(QThread):
    progress_update = pyqtSignal(int)
    folder_found = pyqtSignal(object, object)
    scan_complete = pyqtSignal()
    folder_count_update = pyqtSignal(int)
    
    def __init__(self, root_path, size_threshold_mb, exclude_dirs):
        super().__init__()
        self.root_path = root_path
        self.size_threshold_mb = size_threshold_mb
        self.size_threshold = size_threshold_mb * 1024 * 1024
        self.exclude_dirs = exclude_dirs
        self.is_running = True
        self.path_cache = path_cache  # Используем глобальный экземпляр
        
    def run(self):
        try:
            # Проверяем наличие кешированных данных
            cached_folders = self.path_cache.get_cached_folders(str(self.root_path))
            if cached_folders is not None:
                # Используем кешированные данные
                total_folders = len(cached_folders)
                self.folder_count_update.emit(total_folders)
                
                for folder_data in cached_folders:
                    if not self.is_running:
                        return
                    folder_path = Path(folder_data['path'])
                    folder_size = folder_data['size']
                    if folder_size > self.size_threshold:
                        self.folder_found.emit(folder_path, folder_size)
                
                self.progress_update.emit(100)
                return
            
            # Если кеш отсутствует или устарел, выполняем сканирование
            all_folders = []
            for dirpath, dirnames, _ in os.walk(self.root_path):
                path = Path(dirpath)
                if not is_excluded(path, self.exclude_dirs):
                    all_folders.append(path)
                if not self.is_running:
                    return
            
            total_folders = len(all_folders)
            self.folder_count_update.emit(total_folders)
            
            # Сохраняем результаты сканирования для кеширования
            folders_to_cache = []
            
            # Теперь сканируем каждую папку с обновлением прогресса
            processed = 0
            for folder in all_folders:
                if not self.is_running:
                    break
                    
                try:
                    # Используем правильное имя функции из C++ модуля
                    size = fs_cpp.get_folder_size(str(folder))
                    # Переводим порог в байты (MB * 1024 * 1024)
                    size_threshold_bytes = self.size_threshold_mb * 1024 * 1024
                    if size > size_threshold_bytes:
                        self.folder_found.emit(folder, size)
                        # Добавляем папку в список для кеширования
                        folders_to_cache.append({
                            'path': str(folder),
                            'size': size
                        })
                except Exception as e:
                    print(f"Ошибка при обработке папки {folder}: {e}")
                    continue
                    
                processed += 1
                self.progress_update.emit(int(processed * 100 / total_folders))
                
                # Даем время для обработки событий GUI
                QThread.msleep(1)
                
            # Сохраняем результаты в кеш после успешного сканирования
            self.path_cache.cache_folders(str(self.root_path), folders_to_cache)
                
        except Exception as e:
            print(f"Ошибка сканирования: {e}")
        finally:
            self.scan_complete.emit()
        
    def stop(self):
        self.is_running = False

# Делегат для стилизации ячеек таблицы
class ColorDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() == 1:  # Колонка с размером
            size_text = index.data()
            if 'ГБ' in size_text:
                painter.fillRect(option.rect, QColor(255, 200, 200, 100))
            elif 'МБ' in size_text and float(size_text.split()[0]) > 500:
                painter.fillRect(option.rect, QColor(255, 230, 200, 100))
        
        super().paint(painter, option, index)

class CleanerThread(QThread):
    progress_updated = pyqtSignal(dict)
    finished = pyqtSignal()

    def run(self):
        cleaner = SystemCleaner()
        results = cleaner.clean_system()
        self.progress_updated.emit(results)
        self.finished.emit()

class SettingsWidget(QWidget):
    """Виджет настроек приложения"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Группа общих настроек
        general_group = QGroupBox("Общие настройки")
        general_layout = QVBoxLayout()
        
        # Автозапуск
        self.autostart_check = QCheckBox("Запускать при старте Windows")
        general_layout.addWidget(self.autostart_check)
        
        # Сворачивание в трей
        self.minimize_to_tray_check = QCheckBox("Сворачивать в трей вместо закрытия")
        general_layout.addWidget(self.minimize_to_tray_check)
        
        # Уведомления
        self.notifications_check = QCheckBox("Показывать уведомления")
        general_layout.addWidget(self.notifications_check)
        
        general_group.setLayout(general_layout)
        layout.addWidget(general_group)
        
        # Группа настроек мониторинга
        monitoring_group = QGroupBox("Настройки мониторинга")
        monitoring_layout = QVBoxLayout()
        
        # Интервал проверки
        check_interval_layout = QHBoxLayout()
        check_interval_layout.addWidget(QLabel("Интервал проверки:"))
        self.check_interval_spin = QSpinBox()
        self.check_interval_spin.setRange(1, 60)
        self.check_interval_spin.setValue(5)
        self.check_interval_spin.setSuffix(" мин")
        check_interval_layout.addWidget(self.check_interval_spin)
        check_interval_layout.addStretch()
        monitoring_layout.addLayout(check_interval_layout)
        
        # Порог предупреждения о диске
        disk_threshold_layout = QHBoxLayout()
        disk_threshold_layout.addWidget(QLabel("Порог предупреждения о заполнении диска:"))
        self.disk_threshold_spin = QSpinBox()
        self.disk_threshold_spin.setRange(50, 95)
        self.disk_threshold_spin.setValue(85)
        self.disk_threshold_spin.setSuffix("%")
        disk_threshold_layout.addWidget(self.disk_threshold_spin)
        disk_threshold_layout.addStretch()
        monitoring_layout.addLayout(disk_threshold_layout)
        
        # Порог размера временных файлов
        temp_threshold_layout = QHBoxLayout()
        temp_threshold_layout.addWidget(QLabel("Порог предупреждения о временных файлах:"))
        self.temp_threshold_spin = QSpinBox()
        self.temp_threshold_spin.setRange(100, 10000)
        self.temp_threshold_spin.setValue(1000)
        self.temp_threshold_spin.setSuffix(" МБ")
        temp_threshold_layout.addWidget(self.temp_threshold_spin)
        temp_threshold_layout.addStretch()
        monitoring_layout.addLayout(temp_threshold_layout)
        
        monitoring_group.setLayout(monitoring_layout)
        layout.addWidget(monitoring_group)
        
        # Группа настроек очистки
        cleanup_group = QGroupBox("Настройки очистки")
        cleanup_layout = QVBoxLayout()
        
        # Автоматическая очистка
        self.auto_cleanup_check = QCheckBox("Автоматическая очистка при достижении порога")
        cleanup_layout.addWidget(self.auto_cleanup_check)
        
        # Защита системных файлов
        self.protect_system_check = QCheckBox("Защита системных файлов и папок")
        self.protect_system_check.setChecked(True)
        self.protect_system_check.setEnabled(False)  # Всегда включено
        cleanup_layout.addWidget(self.protect_system_check)
        
        # Подтверждение удаления
        self.confirm_deletion_check = QCheckBox("Запрашивать подтверждение при удалении")
        self.confirm_deletion_check.setChecked(True)
        cleanup_layout.addWidget(self.confirm_deletion_check)
        
        cleanup_group.setLayout(cleanup_layout)
        layout.addWidget(cleanup_group)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_settings)
        buttons_layout.addWidget(save_button)
        
        reset_button = QPushButton("Сбросить")
        reset_button.clicked.connect(self.reset_settings)
        buttons_layout.addWidget(reset_button)
        
        layout.addLayout(buttons_layout)
        layout.addStretch()
        
        # Подсказка внизу
        hint_label = QLabel("* Некоторые настройки вступят в силу после перезапуска программы")
        hint_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(hint_label)
        
    def load_settings(self):
        """Загружает настройки из файла конфигурации"""
        settings = QSettings("SkripClean", "Settings")
        
        # Загружаем общие настройки
        self.autostart_check.setChecked(settings.value("autostart", False, type=bool))
        self.minimize_to_tray_check.setChecked(settings.value("minimize_to_tray", True, type=bool))
        self.notifications_check.setChecked(settings.value("notifications", True, type=bool))
        
        # Загружаем настройки мониторинга
        self.check_interval_spin.setValue(settings.value("check_interval", 5, type=int))
        self.disk_threshold_spin.setValue(settings.value("disk_threshold", 85, type=int))
        self.temp_threshold_spin.setValue(settings.value("temp_threshold", 1000, type=int))
        
        # Загружаем настройки очистки
        self.auto_cleanup_check.setChecked(settings.value("auto_cleanup", False, type=bool))
        self.confirm_deletion_check.setChecked(settings.value("confirm_deletion", True, type=bool))
        
    def save_settings(self):
        """Сохраняет настройки в файл конфигурации"""
        settings = QSettings("SkripClean", "Settings")
        
        # Сохраняем общие настройки
        settings.setValue("autostart", self.autostart_check.isChecked())
        settings.setValue("minimize_to_tray", self.minimize_to_tray_check.isChecked())
        settings.setValue("notifications", self.notifications_check.isChecked())
        
        # Сохраняем настройки мониторинга
        settings.setValue("check_interval", self.check_interval_spin.value())
        settings.setValue("disk_threshold", self.disk_threshold_spin.value())
        settings.setValue("temp_threshold", self.temp_threshold_spin.value())
        
        # Сохраняем настройки очистки
        settings.setValue("auto_cleanup", self.auto_cleanup_check.isChecked())
        settings.setValue("confirm_deletion", self.confirm_deletion_check.isChecked())
        
        # Применяем настройки автозапуска
        self.apply_autostart_settings()
        
        QMessageBox.information(self, "Настройки", "Настройки успешно сохранены")
        
    def reset_settings(self):
        """Сбрасывает настройки на значения по умолчанию"""
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите сбросить все настройки на значения по умолчанию?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Сбрасываем общие настройки
            self.autostart_check.setChecked(False)
            self.minimize_to_tray_check.setChecked(True)
            self.notifications_check.setChecked(True)
            
            # Сбрасываем настройки мониторинга
            self.check_interval_spin.setValue(5)
            self.disk_threshold_spin.setValue(85)
            self.temp_threshold_spin.setValue(1000)
            
            # Сбрасываем настройки очистки
            self.auto_cleanup_check.setChecked(False)
            self.confirm_deletion_check.setChecked(True)
            
            # Сохраняем сброшенные настройки
            self.save_settings()
            
    def apply_autostart_settings(self):
        """Применяет настройки автозапуска"""
        import winreg
        
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "SkripClean"
        
        try:
            if self.autostart_check.isChecked():
                # Добавляем программу в автозапуск
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
                app_path = sys.argv[0]
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
                winreg.CloseKey(key)
            else:
                # Удаляем программу из автозапуска
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
                try:
                    winreg.DeleteValue(key, app_name)
                except WindowsError:
                    pass  # Значение уже отсутствует
                winreg.CloseKey(key)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось изменить настройки автозапуска: {str(e)}")

# Основное окно приложения
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SkripClean - Очистка диска")
        self.setMinimumSize(800, 600)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {BACKGROUND_COLOR}; color: {TEXT_COLOR}; }}
            QPushButton {{ 
                background-color: {PRIMARY_COLOR}; 
                color: white; 
                border: none; 
                padding: 8px 16px; 
                border-radius: 4px; 
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {SECONDARY_COLOR}; }}
            QPushButton#deleteButton {{ background-color: {ACCENT_COLOR}; }}
            QPushButton#deleteButton:hover {{ background-color: #c1121f; }}
            QProgressBar {{ 
                border: 1px solid #bbb; 
                border-radius: 4px; 
                text-align: center; 
                background-color: white;
            }}
            QProgressBar::chunk {{ 
                background-color: {PRIMARY_COLOR}; 
                border-radius: 3px; 
            }}
            QTableWidget {{ 
                border: 1px solid #ddd; 
                border-radius: 4px; 
                gridline-color: #f0f0f0; 
                selection-background-color: {SECONDARY_COLOR}; 
                selection-color: white;
            }}
            QHeaderView::section {{ 
                background-color: {PRIMARY_COLOR}; 
                color: white; 
                padding: 6px; 
                border: none; 
            }}
            QSpinBox, QComboBox {{ 
                border: 1px solid #bbb; 
                border-radius: 4px; 
                padding: 4px; 
                background-color: white; 
            }}
        """)
        
        self.init_ui()
        self.scan_worker = None
        self.large_folders = []
        
    def init_ui(self):
        # Создаем центральный виджет
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Заголовок
        title_label = QLabel("SkripClean")
        title_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {PRIMARY_COLOR}; margin-bottom: 10px;")
        main_layout.addWidget(title_label)
        
        # Описание
        desc_label = QLabel("Поиск и удаление больших папок на диске")
        desc_label.setStyleSheet("font-size: 14px; margin-bottom: 20px;")
        main_layout.addWidget(desc_label)
        
        # Создаем виджет с вкладками
        tab_widget = QTabWidget()
        
        # Создаем виджет для основной функциональности
        disk_cleanup_widget = QWidget()
        disk_cleanup_layout = QVBoxLayout(disk_cleanup_widget)
        
        # Перемещаем существующие элементы в layout вкладки очистки диска
        settings_layout = QHBoxLayout()
        
        # Выбор диска
        drive_label = QLabel("Выберите диск или папку:")
        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(100)
        
        # Заполняем список доступных дисков
        available_drives = [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
        self.drive_combo.addItems(available_drives)
        
        # Кнопка выбора папки
        self.folder_button = QPushButton("Выбрать папку")
        self.folder_button.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        self.folder_button.clicked.connect(self.select_folder)
        
        # Выбор минимального размера
        size_label = QLabel("Минимальный размер папки (МБ):")
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 10000)
        self.size_spin.setValue(100)
        self.size_spin.setSuffix(" МБ")
        
        # Добавляем виджеты в layout
        settings_layout.addWidget(drive_label)
        settings_layout.addWidget(self.drive_combo)
        settings_layout.addWidget(self.folder_button)
        settings_layout.addSpacing(20)
        settings_layout.addWidget(size_label)
        settings_layout.addWidget(self.size_spin)
        
        disk_cleanup_layout.addLayout(settings_layout)
        
        # Кнопки сканирования
        scan_layout = QHBoxLayout()
        self.scan_button = QPushButton("Начать сканирование")
        self.scan_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.scan_button.clicked.connect(self.start_scan)
        self.scan_button.setMinimumHeight(40)
        
        self.stop_button = QPushButton("Остановить")
        self.stop_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserStop))
        self.stop_button.clicked.connect(self.stop_scan)
        self.stop_button.setEnabled(False)
        
        self.ai_button = QPushButton("AI Ассистент")
        self.ai_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.ai_button.clicked.connect(self.show_ai_assistant)
        self.ai_button.setEnabled(False)
        
        scan_layout.addWidget(self.scan_button)
        scan_layout.addWidget(self.stop_button)
        scan_layout.addWidget(self.ai_button)
        disk_cleanup_layout.addLayout(scan_layout)
        
        # Прогресс сканирования
        progress_layout = QVBoxLayout()
        self.progress_label = QLabel("Готов к сканированию")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        disk_cleanup_layout.addLayout(progress_layout)
        
        # Таблица с результатами
        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["Путь", "Размер", "Действия"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setItemDelegate(ColorDelegate())
        
        disk_cleanup_layout.addWidget(self.results_table)
        
        # Статус
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-style: italic; color: #666;")
        disk_cleanup_layout.addWidget(self.status_label)
        
        # Добавляем вкладки
        self.tabs = tab_widget
        self.tabs.addTab(disk_cleanup_widget, "Очистка диска")
        self.tabs.addTab(AutorunManager(), "Управление автозагрузкой")
        
        # Добавляем вкладку очистки системы
        self.system_cleaner_tab = QWidget()
        self.tabs.addTab(self.system_cleaner_tab, "Очистка системы")
        self.setup_cleaner_tab()
        
        # Добавляем вкладку управления программами
        program_uninstaller = ProgramUninstallerWidget(self)
        self.tabs.addTab(program_uninstaller, "Управление программами")
        
        # Добавляем вкладку настроек
        settings_widget = SettingsWidget(self)
        self.tabs.addTab(settings_widget, "Параметры")
        
        main_layout.addWidget(self.tabs)
        
        self.setCentralWidget(central_widget)
        
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сканирования")
        if folder:
            if self.drive_combo.findText(folder) == -1:
                self.drive_combo.addItem(folder)
            self.drive_combo.setCurrentText(folder)
    
    def start_scan(self):
        # Получаем выбранный путь и минимальный размер
        root_path = self.drive_combo.currentText()
        size_threshold_mb = self.size_spin.value()
        
        # Проверяем, существует ли путь
        if not os.path.exists(root_path):
            QMessageBox.warning(self, "Ошибка", "Указанный путь не существует.")
            return
        
        # Очищаем предыдущие результаты
        self.results_table.setRowCount(0)
        self.large_folders = []
        
        # Устанавливаем исключенные папки
        exclude_dirs = {
            'Windows', 'Program Files', 'Program Files (x86)', 'ProgramData',
            'System Volume Information', '$Recycle.Bin', 'AppData'
        }
        
        # Обновляем интерфейс
        self.scan_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Подготовка к сканированию...")
        self.status_label.setText("Сканирование запущено...")
        
        # Запускаем сканирование в отдельном потоке
        self.scan_worker = ScanWorker(root_path, size_threshold_mb, exclude_dirs)
        self.scan_worker.progress_update.connect(self.update_progress)
        self.scan_worker.folder_found.connect(self.add_folder_to_results)
        self.scan_worker.scan_complete.connect(self.scan_finished)
        self.scan_worker.folder_count_update.connect(self.update_folder_count)
        self.scan_worker.start()
    
    def update_folder_count(self, count):
        self.progress_label.setText(f"Сканирование папок: найдено {count} папок для проверки")
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def add_folder_to_results(self, path, size):
        # Добавляем папку в список
        self.large_folders.append((path, size))
        
        # Добавляем строку в таблицу
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        
        # Путь
        path_item = QTableWidgetItem(str(path))
        self.results_table.setItem(row, 0, path_item)
        
        # Размер
        size_item = QTableWidgetItem(format_size(size))
        size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.results_table.setItem(row, 1, size_item)
        
        # Кнопка удаления
        delete_button = QPushButton("Удалить")
        delete_button.setObjectName("deleteButton")
        delete_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        delete_button.clicked.connect(lambda: self.delete_folder(row))
        
        self.results_table.setCellWidget(row, 2, delete_button)
        
        # Обновляем статус
        self.status_label.setText(f"Найдено папок: {len(self.large_folders)}")
    
    def delete_folder(self, row):
        path = self.results_table.item(row, 0).text()
        size = self.results_table.item(row, 1).text()
        
        # Запрашиваем подтверждение
        reply = QMessageBox.question(
            self, 
            "Подтверждение удаления", 
            f"Вы уверены, что хотите удалить папку:\n{path}\nРазмер: {size}",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Удаляем папку
            if delete_folder(Path(path)):
                # Удаляем строку из таблицы
                self.results_table.removeRow(row)
                # Удаляем из списка
                self.large_folders.pop(row)
                # Обновляем статус
                self.status_label.setText(f"Папка удалена: {path}")
            else:
                QMessageBox.warning(self, "Ошибка", f"Не удалось удалить папку {path}")
    
    def stop_scan(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.status_label.setText("Сканирование остановлено пользователем")
            self.stop_button.setEnabled(False)
            # Ждем завершения потока
            QTimer.singleShot(500, self.check_worker_finished)
    
    def check_worker_finished(self):
        if self.scan_worker and self.scan_worker.isRunning():
            # Еще не завершился, проверим позже
            QTimer.singleShot(500, self.check_worker_finished)
        else:
            self.scan_button.setEnabled(True)
    
    def scan_finished(self):
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_bar.setValue(100)
        self.progress_label.setText("Сканирование завершено")
        
        if not self.large_folders:
            self.status_label.setText("Папки, превышающие указанный размер, не найдены")
            self.ai_button.setEnabled(False)  # Отключаем кнопку AI, если нет результатов
        else:
            self.status_label.setText(f"Найдено {len(self.large_folders)} папок, превышающих указанный размер")
            self.ai_button.setEnabled(True)  # Включаем кнопку AI, если есть результаты
    
    def show_ai_assistant(self):
        """Показывает диалоговое окно AI ассистента для анализа папок."""
        if not self.large_folders:
            QMessageBox.information(self, "Информация", "Нет папок для анализа. Сначала выполните сканирование.")
            return
        
        # Подготавливаем список папок для анализа в формате, который ожидает AI ассистент
        folders_for_analysis = []
        for path, size in self.large_folders:
            formatted_size = format_size(size)
            folders_for_analysis.append((str(path), size, formatted_size))
        
        # Вызываем диалоговое окно AI ассистента
        show_ai_assistant_dialog(self, folders_for_analysis)

    def setup_cleaner_tab(self):
        layout = QVBoxLayout()

        # Добавляем текст о бета-тестировании
        beta_label = QLabel(
            "Функция в бета-тестировании, если возникнут ошибки, просьба отправить их разработчику @solecoss")
        beta_label.setStyleSheet(f"font-size: 12px; color: {TEXT_COLOR}; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(beta_label)


        # Создаем разделенный интерфейс: слева фильтры, справа результаты
        splitter = QHBoxLayout()
        
        # Левая панель с фильтрами
        filters_widget = QWidget()
        filters_layout = QVBoxLayout(filters_widget)
        
        # Группы фильтров
        self.filter_groups = {
            "Windows": {
                "Корзина": True,
                "Временные файлы Windows": True,
                "Журнал Windows": True,
                "Буфер обмена": True,
                "Память дампов": True,
                "Журналы ошибок": True,
                "Кэш DNS": True,
                "Недавние документы": True
            },
            "Браузеры": {
                "Microsoft Edge - Интернет-кэш": True,
                "Microsoft Edge - Журнал посещений": True,
                "Microsoft Edge - Cookie-файлы": True,
                "Microsoft Edge - История загрузок": True,
                "Microsoft Edge - Сеанс": True,
                "Internet Explorer - Временные файлы": True,
                "Internet Explorer - Журнал посещений": True,
                "Internet Explorer - Cookie-файлы": True
            },
            "Приложения": {
                "Проводник Windows - Недавние документы": True,
                "Проводник Windows - Эскизы": True,
                "Проводник Windows - Кэш": True,
                "Microsoft Office - Временные файлы": True,
                "Microsoft Office - Автовосстановление": True
            }
        }

        # Создаем виджеты для каждой группы фильтров
        for group_name, filters in self.filter_groups.items():
            group_box = QGroupBox(group_name)
            group_layout = QVBoxLayout()
            
            # Кнопка "Выбрать все" для группы
            select_all_btn = QPushButton("Выбрать все")
            select_all_btn.setCheckable(True)
            select_all_btn.setChecked(True)
            select_all_btn.clicked.connect(lambda checked, g=group_name: self.toggle_group(g, checked))
            group_layout.addWidget(select_all_btn)
            
            # Добавляем чекбоксы для каждого фильтра
            for filter_name in filters:
                checkbox = QCheckBox(filter_name)
                checkbox.setChecked(True)
                group_layout.addWidget(checkbox)
                
            group_box.setLayout(group_layout)
            filters_layout.addWidget(group_box)
        
        # Добавляем растягивающийся спейсер в конец
        filters_layout.addStretch()
        
        # Правая панель с результатами
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        
        # Заголовок результатов
        results_header = QLabel("Сведения об удаляемых файлах")
        results_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        results_layout.addWidget(results_header)
        
        # Дерево результатов
        self.cleanup_tree = QTreeWidget()
        self.cleanup_tree.setHeaderLabels(["Элемент", "Размер", "Количество"])
        self.cleanup_tree.setColumnWidth(0, 300)
        self.cleanup_tree.setColumnWidth(1, 100)
        results_layout.addWidget(self.cleanup_tree)
        
        # Прогресс бар
        self.cleanup_progress = QProgressBar()
        self.cleanup_progress.setTextVisible(True)
        self.cleanup_progress.setFormat("Готов к очистке")
        results_layout.addWidget(self.cleanup_progress)
        
        # Кнопки действий
        buttons_layout = QHBoxLayout()
        
        # Кнопка анализа
        self.analyze_button = QPushButton("Анализ")
        self.analyze_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.analyze_button.clicked.connect(self.analyze_system)
        buttons_layout.addWidget(self.analyze_button)
        
        # Кнопка очистки
        self.cleanup_button = QPushButton("Очистка")
        self.cleanup_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.cleanup_button.clicked.connect(self.start_cleanup)
        self.cleanup_button.setEnabled(False)
        buttons_layout.addWidget(self.cleanup_button)
        
        results_layout.addLayout(buttons_layout)
        
        # Добавляем панели в сплиттер
        splitter.addWidget(filters_widget)
        splitter.addWidget(results_widget)
        
        # Устанавливаем соотношение размеров панелей (40:60)
        filters_widget.setMinimumWidth(300)
        results_widget.setMinimumWidth(400)
        
        layout.addLayout(splitter)
        self.system_cleaner_tab.setLayout(layout)

    def toggle_group(self, group_name: str, checked: bool):
        """Включает или выключает все фильтры в группе"""
        group_box = None
        for i in range(self.system_cleaner_tab.layout().count()):
            widget = self.system_cleaner_tab.layout().itemAt(i).widget()
            if isinstance(widget, QGroupBox) and widget.title() == group_name:
                group_box = widget
                break
                
        if group_box:
            for i in range(group_box.layout().count()):
                widget = group_box.layout().itemAt(i).widget()
                if isinstance(widget, QCheckBox):
                    widget.setChecked(checked)

    def analyze_system(self):
        """Запускает анализ системы"""
        self.analyze_button.setEnabled(False)
        self.cleanup_button.setEnabled(False)
        self.cleanup_progress.setValue(0)
        self.cleanup_progress.setFormat("Анализ системы...")
        
        # Запускаем анализ в отдельном потоке
        self.cleaner_thread = CleanerThread()
        self.cleaner_thread.progress_updated.connect(self.update_cleanup_results)
        self.cleaner_thread.finished.connect(self.analysis_finished)
        self.cleaner_thread.start()

    def start_cleanup(self):
        """Запускает процесс очистки системы"""
        reply = QMessageBox.question(
            self,
            'Подтверждение',
            'Вы уверены, что хотите начать очистку? Этот процесс нельзя отменить.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.analyze_button.setEnabled(False)
            self.cleanup_button.setEnabled(False)
            self.cleanup_progress.setValue(0)
            self.cleanup_progress.setFormat("Выполняется очистка...")
            
            # Запускаем очистку в отдельном потоке
            self.cleaner_thread = CleanerThread()
            self.cleaner_thread.progress_updated.connect(self.update_cleanup_results)
            self.cleaner_thread.finished.connect(self.cleanup_finished)
            self.cleaner_thread.start()

    def analysis_finished(self):
        """Обработка завершения анализа"""
        self.analyze_button.setEnabled(True)
        self.cleanup_button.setEnabled(True)
        self.cleanup_progress.setRange(0, 100)
        self.cleanup_progress.setValue(100)
        self.cleanup_progress.setFormat("Анализ завершен")

    def update_cleanup_results(self, results):
        """Обновляет результаты в дереве"""
        self.cleanup_tree.clear()
        total_size = 0
        total_files = 0
        
        for category, data in results.items():
            category_item = QTreeWidgetItem(self.cleanup_tree)
            category_item.setText(0, category)
            size = data['cleaned_size']
            files = data['files_removed']
            category_item.setText(1, SystemCleaner().get_size_format(size))
            category_item.setText(2, str(files))
            total_size += size
            total_files += files
            
        # Добавляем итоговую строку
        total_item = QTreeWidgetItem(self.cleanup_tree)
        total_item.setText(0, "ИТОГО")
        total_item.setText(1, SystemCleaner().get_size_format(total_size))
        total_item.setText(2, str(total_files))
        total_item.setBackground(0, QColor(240, 240, 240))
        total_item.setBackground(1, QColor(240, 240, 240))
        total_item.setBackground(2, QColor(240, 240, 240))
        
        # Разворачиваем все элементы
        self.cleanup_tree.expandAll()
        
    def cleanup_finished(self):
        """Обработка завершения очистки"""
        self.analyze_button.setEnabled(True)
        self.cleanup_button.setEnabled(True)
        self.cleanup_progress.setRange(0, 100)
        self.cleanup_progress.setValue(100)
        self.cleanup_progress.setFormat("Очистка завершена")

# Запуск приложения
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Используем стиль Fusion для более современного вида
    
    # Показываем диалог с отказом от ответственности
    disclaimer = DisclaimerDialog()
    if disclaimer.exec_() != QDialog.Accepted:
        sys.exit(0)
    
    # Устанавливаем иконку приложения
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon1.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()