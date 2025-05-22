import os
import sys
import winreg
import subprocess
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

import win32com.client
from win32com.client import Dispatch
import win32api
import win32con
import win32gui
import win32process
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
                           QMessageBox, QProgressBar, QComboBox, QCheckBox, QLineEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon

@dataclass
class Program:
    name: str
    publisher: str
    install_date: str
    version: str
    uninstall_string: str
    install_location: str
    is_system: bool
    size: int

class ProgramManager:
    def __init__(self):
        self.programs: List[Program] = []
        self.system_apps_path = "C:\\Windows\\SystemApps"
        
    def get_installed_programs(self) -> List[Program]:
        """Получает список установленных программ из реестра"""
        programs = []
        
        # Пути в реестре для поиска программ
        paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        
        for reg_path in paths:
            try:
                # Открываем раздел реестра
                registry = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
                key = winreg.OpenKey(registry, reg_path)
                
                # Перебираем все подразделы
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        
                        try:
                            name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            uninstall_string = winreg.QueryValueEx(subkey, "UninstallString")[0]
                            
                            # Дополнительная информация (может отсутствовать)
                            try:
                                publisher = winreg.QueryValueEx(subkey, "Publisher")[0]
                            except:
                                publisher = "Неизвестно"
                                
                            try:
                                install_date = winreg.QueryValueEx(subkey, "InstallDate")[0]
                            except:
                                install_date = "Неизвестно"
                                
                            try:
                                version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                            except:
                                version = "Неизвестно"
                                
                            try:
                                install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                            except:
                                install_location = "Неизвестно"
                                
                            try:
                                size = winreg.QueryValueEx(subkey, "EstimatedSize")[0] * 1024  # Конвертируем в байты
                            except:
                                size = 0
                                
                            # Проверяем, является ли программа системной
                            is_system = (
                                install_location.lower().startswith("c:\\windows") or
                                install_location.lower().startswith("c:\\program files\\windowsapps") or
                                "microsoft" in publisher.lower()
                            )
                            
                            program = Program(
                                name=name,
                                publisher=publisher,
                                install_date=install_date,
                                version=version,
                                uninstall_string=uninstall_string,
                                install_location=install_location,
                                is_system=is_system,
                                size=size
                            )
                            
                            programs.append(program)
                            
                        except WindowsError:
                            continue
                            
                    finally:
                        try:
                            winreg.CloseKey(subkey)
                        except:
                            pass
                            
            except WindowsError:
                continue
                
            finally:
                try:
                    winreg.CloseKey(key)
                    winreg.CloseKey(registry)
                except:
                    pass
                    
        self.programs = programs
        return programs
        
    def uninstall_program(self, program: Program) -> bool:
        """Удаляет программу, используя её деинсталлятор"""
        try:
            # Проверяем наличие деинсталлятора
            if not program.uninstall_string:
                return False
                
            # Запускаем деинсталлятор
            if program.uninstall_string.startswith('"'):
                # Если путь в кавычках, разделяем команду и аргументы
                parts = program.uninstall_string.split('" ', 1)
                if len(parts) > 1:
                    cmd = parts[0].strip('"')
                    args = parts[1]
                else:
                    cmd = parts[0].strip('"')
                    args = ""
            else:
                # Если путь без кавычек, используем первое слово как команду
                parts = program.uninstall_string.split(None, 1)
                if len(parts) > 1:
                    cmd = parts[0]
                    args = parts[1]
                else:
                    cmd = parts[0]
                    args = ""
            
            # Запускаем процесс деинсталляции
            subprocess.Popen([cmd, args], shell=True)
            return True
            
        except Exception as e:
            print(f"Ошибка при удалении программы {program.name}: {e}")
            return False
            
    def remove_windows_app(self, app_name: str) -> bool:
        """Удаляет предустановленное приложение Windows"""
        try:
            # Используем PowerShell для удаления приложения
            cmd = f'Get-AppxPackage *{app_name}* | Remove-AppxPackage'
            result = subprocess.run(['powershell', '-Command', cmd], 
                                 capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            print(f"Ошибка при удалении приложения Windows {app_name}: {e}")
            return False

class UninstallWorker(QThread):
    progress_updated = pyqtSignal(str, bool)
    finished = pyqtSignal()
    
    def __init__(self, program: Program):
        super().__init__()
        self.program = program
        self.manager = ProgramManager()
        
    def run(self):
        success = self.manager.uninstall_program(self.program)
        self.progress_updated.emit(
            f"{'Успешно удалено' if success else 'Ошибка удаления'}: {self.program.name}",
            success
        )
        self.finished.emit()

class ProgramUninstallerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = ProgramManager()
        self.init_ui()
        self.load_programs()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Верхняя панель с фильтрами
        filters_layout = QVBoxLayout()
        
        # Первая строка фильтров
        filters_row1 = QHBoxLayout()
        
        # Фильтр по издателю
        self.publisher_combo = QComboBox()
        self.publisher_combo.addItem("Все издатели")
        self.publisher_combo.currentTextChanged.connect(self.filter_programs)
        filters_row1.addWidget(QLabel("Издатель:"))
        filters_row1.addWidget(self.publisher_combo)
        
        # Поиск по названию
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по названию...")
        self.search_input.textChanged.connect(self.filter_programs)
        filters_row1.addWidget(QLabel("Поиск:"))
        filters_row1.addWidget(self.search_input)
        
        filters_row1.addStretch()
        filters_layout.addLayout(filters_row1)
        
        # Вторая строка фильтров
        filters_row2 = QHBoxLayout()
        
        # Фильтр по размеру
        self.size_combo = QComboBox()
        self.size_combo.addItems(["Все размеры", "< 10 МБ", "10-100 МБ", "100-500 МБ", "500 МБ - 1 ГБ", "> 1 ГБ"])
        self.size_combo.currentTextChanged.connect(self.filter_programs)
        filters_row2.addWidget(QLabel("Размер:"))
        filters_row2.addWidget(self.size_combo)
        
        # Фильтр по дате установки
        self.date_combo = QComboBox()
        self.date_combo.addItems([
            "Все даты", 
            "Сегодня",
            "За последнюю неделю",
            "За последний месяц",
            "За последний год"
        ])
        self.date_combo.currentTextChanged.connect(self.filter_programs)
        filters_row2.addWidget(QLabel("Дата установки:"))
        filters_row2.addWidget(self.date_combo)
        
        # Чекбокс для системных программ
        self.show_system_cb = QCheckBox("Показывать системные")
        self.show_system_cb.setChecked(False)
        self.show_system_cb.stateChanged.connect(self.filter_programs)
        filters_row2.addWidget(self.show_system_cb)
        
        # Кнопка обновления
        refresh_btn = QPushButton("Обновить список")
        refresh_btn.clicked.connect(self.load_programs)
        filters_row2.addWidget(refresh_btn)
        
        filters_row2.addStretch()
        filters_layout.addLayout(filters_row2)
        
        layout.addLayout(filters_layout)
        
        # Таблица программ
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Название", "Издатель", "Версия", 
            "Дата установки", "Размер", "Действия"
        ])
        
        # Настройка сортировки
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().sectionClicked.connect(self.handle_sort)
        
        # Настройка размеров колонок
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        
        # Статистика
        self.stats_label = QLabel()
        layout.addWidget(self.stats_label)
        
        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
    def load_programs(self):
        """Загружает список программ в таблицу"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        programs = self.manager.get_installed_programs()
        
        # Собираем уникальных издателей
        publishers = set()
        total_size = 0
        
        for program in programs:
            publishers.add(program.publisher)
            total_size += program.size
            
            if not self.show_system_cb.isChecked() and program.is_system:
                continue
                
            self.add_program_to_table(program)
            
        # Обновляем список издателей
        current_publisher = self.publisher_combo.currentText()
        self.publisher_combo.clear()
        self.publisher_combo.addItem("Все издатели")
        self.publisher_combo.addItems(sorted(publishers))
        
        # Восстанавливаем выбранного издателя
        index = self.publisher_combo.findText(current_publisher)
        if index >= 0:
            self.publisher_combo.setCurrentIndex(index)
            
        # Обновляем статистику
        self.update_statistics(programs)
        self.table.setSortingEnabled(True)
            
    def add_program_to_table(self, program: Program):
        """Добавляет программу в таблицу"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Название
        self.table.setItem(row, 0, QTableWidgetItem(program.name))
        
        # Издатель
        self.table.setItem(row, 1, QTableWidgetItem(program.publisher))
        
        # Версия
        self.table.setItem(row, 2, QTableWidgetItem(program.version))
        
        # Дата установки
        date_item = QTableWidgetItem(program.install_date)
        date_item.setData(Qt.UserRole, program.install_date)  # Для сортировки
        self.table.setItem(row, 3, date_item)
        
        # Размер
        size_text = self.format_size(program.size)
        size_item = QTableWidgetItem(size_text)
        size_item.setData(Qt.UserRole, program.size)  # Для сортировки
        self.table.setItem(row, 4, size_item)
        
        # Кнопка удаления
        uninstall_btn = QPushButton("Удалить")
        uninstall_btn.clicked.connect(lambda checked, p=program: self.uninstall_program(p))
        self.table.setCellWidget(row, 5, uninstall_btn)
            
    def filter_programs(self):
        """Фильтрует программы по выбранным критериям"""
        search_text = self.search_input.text().lower()
        publisher = self.publisher_combo.currentText()
        size_filter = self.size_combo.currentText()
        date_filter = self.date_combo.currentText()
        show_system = self.show_system_cb.isChecked()
        
        for row in range(self.table.rowCount()):
            show_row = True
            
            # Фильтр по названию
            name = self.table.item(row, 0).text().lower()
            if search_text and search_text not in name:
                show_row = False
                
            # Фильтр по издателю
            if publisher != "Все издатели":
                if self.table.item(row, 1).text() != publisher:
                    show_row = False
                    
            # Фильтр по размеру
            size = self.table.item(row, 4).data(Qt.UserRole)
            if not self.check_size_filter(size, size_filter):
                show_row = False
                
            # Фильтр по дате
            date = self.table.item(row, 3).data(Qt.UserRole)
            if not self.check_date_filter(date, date_filter):
                show_row = False
                    
            self.table.setRowHidden(row, not show_row)
            
        self.update_statistics()
            
    def check_size_filter(self, size: int, filter_text: str) -> bool:
        """Проверяет соответствие размера фильтру"""
        if filter_text == "Все размеры":
            return True
        elif filter_text == "< 10 МБ":
            return size < 10 * 1024 * 1024
        elif filter_text == "10-100 МБ":
            return 10 * 1024 * 1024 <= size < 100 * 1024 * 1024
        elif filter_text == "100-500 МБ":
            return 100 * 1024 * 1024 <= size < 500 * 1024 * 1024
        elif filter_text == "500 МБ - 1 ГБ":
            return 500 * 1024 * 1024 <= size < 1024 * 1024 * 1024
        elif filter_text == "> 1 ГБ":
            return size >= 1024 * 1024 * 1024
        return True
            
    def check_date_filter(self, date_str: str, filter_text: str) -> bool:
        """Проверяет соответствие даты фильтру"""
        if filter_text == "Все даты" or date_str == "Неизвестно":
            return True
            
        try:
            from datetime import datetime, timedelta
            
            # Преобразуем строку даты в объект datetime
            install_date = datetime.strptime(date_str, "%Y%m%d")
            today = datetime.now()
            
            if filter_text == "Сегодня":
                return install_date.date() == today.date()
            elif filter_text == "За последнюю неделю":
                return (today - install_date).days <= 7
            elif filter_text == "За последний месяц":
                return (today - install_date).days <= 30
            elif filter_text == "За последний год":
                return (today - install_date).days <= 365
                
        except ValueError:
            return False
            
        return True
            
    def handle_sort(self, column: int):
        """Обрабатывает сортировку по колонке"""
        self.table.sortItems(column, Qt.AscendingOrder)
            
    def update_statistics(self, programs=None):
        """Обновляет статистику"""
        visible_count = 0
        visible_size = 0
        
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                visible_count += 1
                visible_size += self.table.item(row, 4).data(Qt.UserRole)
                
        total_count = len(programs) if programs else self.table.rowCount()
        self.stats_label.setText(
            f"Показано: {visible_count} из {total_count} программ. "
            f"Общий размер: {self.format_size(visible_size)}"
        )
            
    def uninstall_program(self, program: Program):
        """Запускает процесс удаления программы"""
        reply = QMessageBox.question(
            self,
            'Подтверждение',
            f'Вы уверены, что хотите удалить программу {program.name}?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            
            # Запускаем удаление в отдельном потоке
            self.uninstall_worker = UninstallWorker(program)
            self.uninstall_worker.progress_updated.connect(self.handle_uninstall_progress)
            self.uninstall_worker.finished.connect(self.handle_uninstall_finished)
            self.uninstall_worker.start()
            
    def handle_uninstall_progress(self, message: str, success: bool):
        """Обрабатывает прогресс удаления"""
        if success:
            QMessageBox.information(self, "Успех", message)
        else:
            QMessageBox.warning(self, "Ошибка", message)
            
    def handle_uninstall_finished(self):
        """Обрабатывает завершение удаления"""
        self.progress_bar.setVisible(False)
        self.load_programs()
        
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Форматирует размер в байтах в человекочитаемый вид"""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} ТБ" 