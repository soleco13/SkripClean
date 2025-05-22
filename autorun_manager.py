import os
import winreg
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                           QPushButton, QHeaderView, QMessageBox, QHBoxLayout,
                           QLineEdit, QComboBox, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

class AutorunManager(QWidget):
    def __init__(self):
        super().__init__()
        self.all_programs = []  # Сохраняем все программы для фильтрации
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Панель фильтров
        filter_layout = QHBoxLayout()
        
        # Поиск по названию
        search_layout = QVBoxLayout()
        search_label = QLabel("Поиск по названию:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Введите название программы...")
        self.search_input.textChanged.connect(self.apply_filters)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        filter_layout.addLayout(search_layout)
        
        # Фильтр по статусу
        status_layout = QVBoxLayout()
        status_label = QLabel("Фильтр по статусу:")
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Все", "Включено", "Отключено"])
        self.status_combo.currentTextChanged.connect(self.apply_filters)
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_combo)
        filter_layout.addLayout(status_layout)
        
        # Фильтр по расположению в реестре
        registry_layout = QVBoxLayout()
        registry_label = QLabel("Расположение в реестре:")
        self.registry_combo = QComboBox()
        self.registry_combo.addItems(["Все", "HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"])
        self.registry_combo.currentTextChanged.connect(self.apply_filters)
        registry_layout.addWidget(registry_label)
        registry_layout.addWidget(self.registry_combo)
        filter_layout.addLayout(registry_layout)
        
        # Кнопка сброса фильтров
        reset_layout = QVBoxLayout()
        reset_label = QLabel("")  # Пустая метка для выравнивания
        self.reset_button = QPushButton("Сбросить фильтры")
        self.reset_button.clicked.connect(self.reset_filters)
        reset_layout.addWidget(reset_label)
        reset_layout.addWidget(self.reset_button)
        filter_layout.addLayout(reset_layout)
        
        layout.addLayout(filter_layout)
        
        # Кнопка обновления списка
        refresh_button = QPushButton("Обновить список")
        refresh_button.clicked.connect(self.load_autorun_programs)
        layout.addWidget(refresh_button)
        
        # Создаем таблицу для отображения программ автозагрузки
        self.table = QTableWidget(0, 5)  # Добавлен столбец для источника
        self.table.setHorizontalHeaderLabels(["Программа", "Путь", "Статус", "Источник", "Действия"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.table)
        
        # Статистика
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.stats_label)
        
        # Загружаем программы автозагрузки
        self.load_autorun_programs()
        
    def load_autorun_programs(self):
        self.table.setRowCount(0)
        self.all_programs.clear()
        
        # Пути реестра для проверки автозагрузки
        registry_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKEY_CURRENT_USER"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKEY_LOCAL_MACHINE")
        ]
        
        total_enabled = 0
        total_disabled = 0
        
        for hkey, reg_path, source in registry_paths:
            try:
                registry_key = winreg.OpenKey(hkey, reg_path, 0, winreg.KEY_READ)
                
                try:
                    index = 0
                    while True:
                        name, value, _ = winreg.EnumValue(registry_key, index)
                        program_info = {
                            'name': name,
                            'path': value,
                            'status': "Включено",
                            'source': source
                        }
                        self.all_programs.append(program_info)
                        total_enabled += 1
                        index += 1
                except WindowsError:
                    pass
                
                winreg.CloseKey(registry_key)
            except WindowsError:
                continue
        
        self.update_table()
        self.update_stats(total_enabled, total_disabled)
        
    def update_stats(self, enabled, disabled):
        total = enabled + disabled
        self.stats_label.setText(
            f"Всего программ: {total} | Включено: {enabled} | Отключено: {disabled}"
        )
        
    def update_table(self, filtered_programs=None):
        programs = filtered_programs if filtered_programs is not None else self.all_programs
        self.table.setRowCount(0)
        
        for program in programs:
            self.add_program_to_table(program)
            
    def add_program_to_table(self, program):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Название программы
        name_item = QTableWidgetItem(program['name'])
        self.table.setItem(row, 0, name_item)
        
        # Путь к программе
        path_item = QTableWidgetItem(program['path'])
        self.table.setItem(row, 1, path_item)
        
        # Статус
        status_item = QTableWidgetItem(program['status'])
        status_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 2, status_item)
        
        # Источник
        source_item = QTableWidgetItem(program['source'])
        source_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, source_item)
        
        # Кнопки управления
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(5, 0, 5, 0)
        
        toggle_button = QPushButton("Отключить" if program['status'] == "Включено" else "Включить")
        toggle_button.clicked.connect(lambda: self.toggle_autorun(row))
        
        delete_button = QPushButton("Удалить")
        delete_button.clicked.connect(lambda: self.delete_autorun(row))
        
        control_layout.addWidget(toggle_button)
        control_layout.addWidget(delete_button)
        
        self.table.setCellWidget(row, 4, control_widget)
        
    def apply_filters(self):
        search_text = self.search_input.text().lower()
        status_filter = self.status_combo.currentText()
        registry_filter = self.registry_combo.currentText()
        
        filtered_programs = []
        
        for program in self.all_programs:
            # Фильтр по поиску
            if search_text and search_text not in program['name'].lower():
                continue
                
            # Фильтр по статусу
            if status_filter != "Все" and program['status'] != status_filter:
                continue
                
            # Фильтр по реестру
            if registry_filter != "Все" and program['source'] != registry_filter:
                continue
                
            filtered_programs.append(program)
            
        self.update_table(filtered_programs)
        
        # Обновляем статистику для отфильтрованных результатов
        enabled = sum(1 for p in filtered_programs if p['status'] == "Включено")
        disabled = sum(1 for p in filtered_programs if p['status'] == "Отключено")
        self.update_stats(enabled, disabled)
        
    def reset_filters(self):
        self.search_input.clear()
        self.status_combo.setCurrentText("Все")
        self.registry_combo.setCurrentText("Все")
        self.update_table()
        
    def toggle_autorun(self, row):
        name = self.table.item(row, 0).text()
        status = self.table.item(row, 2).text()
        source = self.table.item(row, 3).text()
        
        try:
            # Выбираем правильный ключ реестра на основе источника
            hkey = winreg.HKEY_CURRENT_USER if source == "HKEY_CURRENT_USER" else winreg.HKEY_LOCAL_MACHINE
            key = winreg.OpenKey(hkey, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            
            if status == "Включено":
                # Отключаем программу
                winreg.DeleteValue(key, name)
                new_status = "Отключено"
                button_text = "Включить"
            else:
                # Включаем программу
                path = self.table.item(row, 1).text()
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, path)
                new_status = "Включено"
                button_text = "Отключить"
                
            winreg.CloseKey(key)
            
            # Обновляем статус в таблице и списке
            self.table.item(row, 2).setText(new_status)
            self.table.cellWidget(row, 4).findChild(QPushButton).setText(button_text)
            
            # Обновляем статус в all_programs
            for program in self.all_programs:
                if program['name'] == name and program['source'] == source:
                    program['status'] = new_status
                    break
                    
            # Обновляем статистику
            enabled = sum(1 for p in self.all_programs if p['status'] == "Включено")
            disabled = sum(1 for p in self.all_programs if p['status'] == "Отключено")
            self.update_stats(enabled, disabled)
            
        except WindowsError as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось изменить состояние автозагрузки: {str(e)}")
            
    def delete_autorun(self, row):
        name = self.table.item(row, 0).text()
        source = self.table.item(row, 3).text()
        
        reply = QMessageBox.question(self, "Подтверждение",
                                   f"Вы уверены, что хотите удалить '{name}' из автозагрузки?",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                # Выбираем правильный ключ реестра на основе источника
                hkey = winreg.HKEY_CURRENT_USER if source == "HKEY_CURRENT_USER" else winreg.HKEY_LOCAL_MACHINE
                key = winreg.OpenKey(hkey, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, name)
                winreg.CloseKey(key)
                
                # Удаляем из таблицы и списка
                self.table.removeRow(row)
                self.all_programs = [p for p in self.all_programs if not (p['name'] == name and p['source'] == source)]
                
                # Обновляем статистику
                enabled = sum(1 for p in self.all_programs if p['status'] == "Включено")
                disabled = sum(1 for p in self.all_programs if p['status'] == "Отключено")
                self.update_stats(enabled, disabled)
                
            except WindowsError as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось удалить программу из автозагрузки: {str(e)}") 