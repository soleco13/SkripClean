import os
import json
import requests
from pathlib import Path
import time
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                             QAbstractItemView, QTextEdit)
from PyQt5.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot

# Константы для API
API_URL = "https://openrouter.ai/api/v1/chat/completions"

def get_api_key():
    """Возвращает встроенный API ключ."""
    return "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"

# Функция для анализа папки с помощью ИИ
def analyze_folder(folder_path, folder_size, folder_name=None, callback=None):
    """Анализирует папку с помощью ИИ и возвращает рекомендации.
    
    Args:
        folder_path: Путь к папке для анализа
        folder_size: Размер папки в читаемом формате
        folder_name: Имя папки (опционально)
        callback: Функция обратного вызова для потоковой передачи ответа (опционально)
    """
    api_key = get_api_key()
    if not api_key:
        return {
            "error": "API ключ не найден. Пожалуйста, добавьте OPENROUTER_API_KEY в переменные окружения или в файл config.json."
        }
    
    # Если имя папки не указано, используем последнюю часть пути
    if not folder_name:
        folder_name = Path(folder_path).name
    
    # Получаем список файлов в папке (до 10 файлов для примера)
    files = []
    try:
        path = Path(folder_path)
        for item in list(path.iterdir())[:10]:  # Ограничиваем до 10 файлов
            if item.is_file():
                files.append(item.name)
            elif item.is_dir():
                files.append(f"{item.name}/")
    except Exception as e:
        files = [f"Ошибка при получении списка файлов: {e}"]
    
    # Формируем запрос к API
    prompt = f"""Проанализируй папку '{folder_name}' размером {folder_size} и определи, безопасно ли её удалить.

Путь к папке: {folder_path}

Примеры файлов в папке:
{', '.join(files)}

Дай два ответа:
1. Можно ли безопасно удалить эту папку? (да/нет)
2. Объяснение, почему можно или нельзя удалять эту папку.

Ответ должен быть в формате JSON с полями 'safe_to_delete' (boolean) и 'explanation' (string)."""
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://skripclean.app",
        "X-Title": "SkripClean",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "google/gemma-3-27b-it:free",
        "messages": [
            {"role": "system", "content": "Ты - эксперт по анализу файловой системы. Твоя задача - определить, безопасно ли удалить указанную папку, и объяснить причины. Отвечай только в формате JSON с полями 'safe_to_delete' (boolean) и 'explanation' (string)."},
            {"role": "user", "content": prompt}
        ],
        "stream": callback is not None  # Включаем потоковую передачу, если указан callback
    }
    
    try:
        # Если используется потоковая передача
        if callback and callable(callback):
            # Для хранения полного ответа
            full_response = ""
            
            # Отправляем запрос с stream=True для потоковой передачи
            with requests.post(API_URL, headers=headers, json=data, stream=True) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        # Удаляем префикс 'data: ' и обрабатываем JSON
                        line_text = line.decode('utf-8')
                        if line_text.startswith('data: '):
                            line_json = line_text[6:]
                            if line_json == "[DONE]":
                                break
                            
                            try:
                                chunk = json.loads(line_json)
                                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if content:
                                    full_response += content
                                    # Вызываем callback с текущим фрагментом
                                    callback(content, full_response)
                            except json.JSONDecodeError:
                                pass
            
            # Обрабатываем полный ответ так же, как и в неструйном режиме
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', full_response)
                if json_match:
                    ai_json = json.loads(json_match.group(0))
                    return {
                        "safe_to_delete": ai_json.get("safe_to_delete", False),
                        "explanation": ai_json.get("explanation", "Нет объяснения"),
                        "full_response": full_response  # Сохраняем полный ответ
                    }
                else:
                    return {
                        "safe_to_delete": False,
                        "explanation": "Не удалось получить структурированный ответ от ИИ. Рекомендуется проверить папку вручную.",
                        "full_response": full_response  # Сохраняем полный ответ
                    }
            except Exception as e:
                return {
                    "safe_to_delete": False,
                    "explanation": f"Ошибка при обработке ответа ИИ: {e}. Рекомендуется проверить папку вручную.",
                    "full_response": full_response  # Сохраняем полный ответ
                }
        else:
            # Обычный режим без потоковой передачи
            response = requests.post(API_URL, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            ai_response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Пытаемся извлечь JSON из ответа
            try:
                # Ищем JSON в ответе (может быть обернут в код или другой текст)
                import re
                json_match = re.search(r'\{[\s\S]*\}', ai_response)
                if json_match:
                    ai_json = json.loads(json_match.group(0))
                    return {
                        "safe_to_delete": ai_json.get("safe_to_delete", False),
                        "explanation": ai_json.get("explanation", "Нет объяснения"),
                        "full_response": ai_response  # Сохраняем полный ответ
                    }
                else:
                    return {
                        "safe_to_delete": False,
                        "explanation": "Не удалось получить структурированный ответ от ИИ. Рекомендуется проверить папку вручную.",
                        "full_response": ai_response  # Сохраняем полный ответ
                    }
            except Exception as e:
                return {
                    "safe_to_delete": False,
                    "explanation": f"Ошибка при обработке ответа ИИ: {e}. Рекомендуется проверить папку вручную.",
                    "full_response": ai_response  # Сохраняем полный ответ
                }
            
    except Exception as e:
        return {
            "error": f"Ошибка при запросе к API: {e}"
        }

# Функция для анализа списка папок
def analyze_folders(folders_list, callback=None):
    """Анализирует список папок и возвращает рекомендации для каждой.
    
    Args:
        folders_list: Список папок для анализа
        callback: Функция обратного вызова для потоковой передачи ответа (опционально)
    """
    results = []
    
    for folder_data in folders_list:
        folder_path, folder_size, formatted_size = folder_data
        
        # Добавляем небольшую задержку между запросами, чтобы не перегружать API
        time.sleep(1)
        
        # Если указан callback, передаем его в analyze_folder
        if callback and callable(callback):
            analysis = analyze_folder(folder_path, formatted_size, callback=callback)
        else:
            analysis = analyze_folder(folder_path, formatted_size)
        
        results.append({
            "path": folder_path,
            "size": formatted_size,
            "analysis": analysis
        })
    
    return results


# Класс диалогового окна AI ассистента
class AIAssistantDialog(QDialog):
    def __init__(self, parent=None, folders_list=None):
        super().__init__(parent)
        self.setWindowTitle("AI Ассистент - Анализ папок")
        self.setMinimumSize(800, 600)
        self.folders_list = folders_list or []
        self.results = []
        self.current_row = -1  # Текущая обрабатываемая строка
        self.full_responses = {}  # Словарь для хранения полных ответов
        
        self.init_ui()
    
    def init_ui(self):
        # Основной layout
        layout = QVBoxLayout(self)
        
        # Заголовок
        title_label = QLabel("AI Ассистент")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Описание
        desc_label = QLabel("Анализ папок с помощью искусственного интеллекта")
        desc_label.setStyleSheet("font-size: 12px; margin-bottom: 15px;")
        layout.addWidget(desc_label)
        
        # Таблица результатов
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Выбор", "Путь", "Размер", "Рекомендация"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results_table.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.results_table)
        
        # Кнопки выбора
        select_buttons_layout = QHBoxLayout()
        
        self.select_all_button = QPushButton("Выбрать всё")
        self.select_all_button.clicked.connect(self.select_all_folders)
        self.select_all_button.setToolTip("Выбрать все папки для анализа")
        select_buttons_layout.addWidget(self.select_all_button)
        
        self.deselect_all_button = QPushButton("Снять выбор")
        self.deselect_all_button.clicked.connect(self.deselect_all_folders)
        self.deselect_all_button.setToolTip("Снять выбор со всех папок")
        select_buttons_layout.addWidget(self.deselect_all_button)
        
        select_buttons_layout.addStretch()
        layout.addLayout(select_buttons_layout)
        
        # Основные кнопки
        buttons_layout = QHBoxLayout()
        
        self.analyze_button = QPushButton("Анализировать выбранные папки")
        self.analyze_button.clicked.connect(self.analyze_selected_folders)
        self.analyze_button.setToolTip("Запустить AI-анализ выбранных папок")
        buttons_layout.addWidget(self.analyze_button)
        
        self.view_full_button = QPushButton("Просмотреть полный комментарий")
        self.view_full_button.clicked.connect(self.show_full_response)
        self.view_full_button.setEnabled(False)
        self.view_full_button.setToolTip("Показать полный анализ выбранной папки")
        buttons_layout.addWidget(self.view_full_button)
        
        self.close_button = QPushButton("Закрыть")
        self.close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.close_button)
        
        layout.addLayout(buttons_layout)
        
        # Статус и прогресс
        status_layout = QHBoxLayout()
        
        # Иконка статуса
        self.status_icon = QLabel("ℹ")
        self.status_icon.setStyleSheet("font-size: 16px; color: #0078D4; min-width: 24px;")
        self.status_icon.setToolTip("Статус операции")
        status_layout.addWidget(self.status_icon)
        
        # Текст статуса
        self.status_label = QLabel("Готов к анализу")
        self.status_label.setStyleSheet("""
            font-style: italic;
            color: #666;
            padding: 5px;
            border-radius: 3px;
            background-color: #f5f5f5;
        """)
        status_layout.addWidget(self.status_label)
        
        # Индикатор прогресса
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet("""
            color: #0078D4;
            font-weight: bold;
            margin-left: 10px;
        """)
        self.progress_label.hide()
        status_layout.addWidget(self.progress_label)
        
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # Справочная информация
        help_text = """❓ Справка:
- Выберите папки для анализа, используя флажки в первой колонке
- Нажмите 'Анализировать' для получения рекомендаций
- После анализа можно просмотреть полный отчёт, выбрав папку"""
        help_label = QLabel(help_text)
        help_label.setStyleSheet("""
            color: #666;
            font-size: 11px;
            padding: 10px;
            background-color: #f8f8f8;
            border-radius: 5px;
            margin-top: 5px;
        """)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Если есть папки для анализа, добавляем их в таблицу
        if self.folders_list:
            self.add_folders_to_table()
            
        # Подключаем обработчик выделения строки в таблице
        self.results_table.itemSelectionChanged.connect(self.on_selection_changed)
    
    def add_folders_to_table(self):
        """Добавляет папки в таблицу."""
        self.results_table.setRowCount(len(self.folders_list))
        
        for row, (folder_path, folder_size, formatted_size) in enumerate(self.folders_list):
            # Чекбокс
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.Checked)  # По умолчанию все выбраны
            checkbox_item.setToolTip("Выберите для анализа этой папки")
            self.results_table.setItem(row, 0, checkbox_item)
            
            # Путь
            path_item = QTableWidgetItem(folder_path)
            path_item.setFlags(path_item.flags() & ~Qt.ItemIsEditable)
            path_item.setToolTip(folder_path)  # Полный путь в подсказке
            self.results_table.setItem(row, 1, path_item)
            
            # Размер
            size_item = QTableWidgetItem(formatted_size)
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
            size_item.setToolTip(f"Размер папки: {formatted_size}")
            self.results_table.setItem(row, 2, size_item)
            
            # Рекомендация (пока пустая)
            recommendation_item = QTableWidgetItem("Нажмите 'Анализировать' для получения рекомендации")
            recommendation_item.setFlags(recommendation_item.flags() & ~Qt.ItemIsEditable)
            recommendation_item.setToolTip("Здесь появится рекомендация после анализа")
            self.results_table.setItem(row, 3, recommendation_item)
    
    def on_selection_changed(self):
        """Обработчик изменения выделения в таблице"""
        selected_rows = self.results_table.selectionModel().selectedRows()
        self.view_full_button.setEnabled(len(selected_rows) > 0)
    
    def show_full_response(self):
        """Показывает полный ответ от ИИ"""
        # Получаем выбранную строку
        selected_rows = self.results_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "Информация", "Выберите папку для просмотра полного анализа")
            return
            
        row = selected_rows[0].row()
        if row not in self.full_responses:
            QMessageBox.information(self, "Информация", "Для этой папки ещё нет полного анализа")
            return

        # Получаем информацию о папке
        folder_path = self.results_table.item(row, 1).text()
        folder_size = self.results_table.item(row, 2).text()
            
        # Создаем диалоговое окно для полного ответа
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Полный анализ папки: {Path(folder_path).name}")
        dialog.setMinimumSize(700, 500)
        
        layout = QVBoxLayout(dialog)
        
        # Информация о папке
        info_layout = QVBoxLayout()
        path_label = QLabel(f"Путь: {folder_path}")
        path_label.setWordWrap(True)
        path_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(path_label)
        
        size_label = QLabel(f"Размер: {folder_size}")
        size_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(size_label)
        
        layout.addLayout(info_layout)
        
        # Разделитель
        separator = QLabel()
        separator.setStyleSheet("background-color: #e0e0e0; min-height: 1px; margin: 10px 0;")
        layout.addWidget(separator)
        
        # Добавляем текстовое поле для отображения ответа
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        
        # Парсим JSON ответ
        try:
            # Пытаемся найти JSON в ответе
            import re
            json_match = re.search(r'\{[\s\S]*\}', self.full_responses[row])
            if json_match:
                try:
                    response = json.loads(json_match.group(0))
                    if isinstance(response, dict):
                        safe_to_delete = response.get('safe_to_delete')
                        explanation = response.get('explanation', 'Нет объяснения')
                        if isinstance(safe_to_delete, bool):
                            formatted_text = f"""РЕКОМЕНДАЦИЯ:

Безопасно удалить: {'✅ Да' if safe_to_delete else '❌ Нет'}

ОБЪЯСНЕНИЕ:

{explanation}"""
                        else:
                            formatted_text = self.full_responses[row]
                    else:
                        formatted_text = self.full_responses[row]
                except json.JSONDecodeError:
                    formatted_text = self.full_responses[row]
            else:
                formatted_text = self.full_responses[row]
        except Exception:
            formatted_text = self.full_responses[row]
        
        text_edit.setPlainText(formatted_text)
        text_edit.setStyleSheet("font-size: 12pt; padding: 10px;")
        layout.addWidget(text_edit)
        
        # Кнопка закрытия
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_button = QPushButton("Закрыть")
        close_button.setMinimumWidth(120)
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        dialog.exec_()
    
    
    @pyqtSlot(int, str, str)
    def update_recommendation(self, row, content, full_response=None):
        """Обновляет рекомендацию в таблице"""
        if row < 0 or row >= self.results_table.rowCount():
            return
            
        # Получаем текущий текст рекомендации
        current_item = self.results_table.item(row, 3)
        if not current_item:
            current_item = QTableWidgetItem("")
            self.results_table.setItem(row, 3, current_item)
        
        # Обновляем текст рекомендации
        current_item.setText(content)
        
        # Сохраняем полный ответ
        if full_response:
            self.full_responses[row] = full_response
            # Включаем кнопку просмотра полного ответа
            self.view_full_button.setEnabled(True)
    
    def stream_callback(self, content, full_response):
        """Callback-функция для потоковой передачи ответа"""
        if self.current_row < 0:
            return
            
        try:
            # Пытаемся найти JSON в ответе
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    response = json.loads(json_match.group(0))
                    if isinstance(response, dict):
                        safe_to_delete = response.get('safe_to_delete')
                        explanation = response.get('explanation', 'Нет объяснения')
                        if isinstance(safe_to_delete, bool):
                            formatted_content = f"{'✅' if safe_to_delete else '❌'} {explanation}"
                        else:
                            formatted_content = content
                    else:
                        formatted_content = content
                except json.JSONDecodeError:
                    formatted_content = content
            else:
                formatted_content = content
        except Exception:
            formatted_content = content
            
        # Обновляем текущую рекомендацию
        self.update_recommendation(self.current_row, formatted_content, full_response)
        
        # Обновляем интерфейс
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
    
    def select_all_folders(self):
        """Выбирает все папки в таблице."""
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
    
    def deselect_all_folders(self):
        """Снимает выбор со всех папок в таблице."""
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
    
    def analyze_selected_folders(self):
        """Анализирует выбранные папки с помощью AI."""
        # Проверяем, есть ли папки для анализа
        if not self.folders_list:
            QMessageBox.warning(self, "Предупреждение", "Нет папок для анализа")
            return
        
        # Получаем список выбранных папок
        selected_folders = []
        for row in range(self.results_table.rowCount()):
            if self.results_table.item(row, 0).checkState() == Qt.Checked:
                selected_folders.append((row, self.folders_list[row]))
        
        if not selected_folders:
            QMessageBox.warning(self, "Предупреждение", "Не выбрано ни одной папки для анализа")
            return
        
        # Обновляем статус
        self.status_label.setText("Подготовка к анализу...")
        self.status_icon.setText("⏳")
        self.status_icon.setStyleSheet("font-size: 16px; color: #0078D4; min-width: 24px;")
        self.progress_label.setText("0%")
        self.progress_label.show()
        self.analyze_button.setEnabled(False)
        self.view_full_button.setEnabled(False)
        
        # Очищаем предыдущие результаты
        self.results = []
        self.full_responses = {}
        
        # Подготавливаем таблицу для отображения результатов
        for row in range(self.results_table.rowCount()):
            if self.results_table.item(row, 0).checkState() == Qt.Checked:
                recommendation_item = QTableWidgetItem("Ожидание анализа...")
                self.results_table.setItem(row, 3, recommendation_item)
        
        # Анализируем выбранные папки по одной, с потоковой передачей ответов
        try:
            for i, (row, folder_data) in enumerate(selected_folders):
                folder_path, folder_size, formatted_size = folder_data
                
                # Устанавливаем текущую обрабатываемую строку
                self.current_row = row
                self.status_label.setText(f"Анализ папки {i+1} из {len(selected_folders)}...")
                self.status_icon.setText("⏳")
                self.status_icon.setStyleSheet("font-size: 16px; color: #0078D4; min-width: 24px;")
                self.progress_label.setText(f"{int((i+1)/len(selected_folders)*100)}%")
                self.progress_label.show()
                
                # Обновляем текст рекомендации
                recommendation_item = self.results_table.item(row, 3)
                if recommendation_item:
                    recommendation_item.setText("Анализ...")
                
                # Анализируем папку с потоковой передачей ответа
                analysis = analyze_folder(folder_path, formatted_size, callback=self.stream_callback)
                
                # Добавляем результат в список
                self.results.append({
                    "path": folder_path,
                    "size": formatted_size,
                    "analysis": analysis
                })
                
                # Обновляем рекомендацию в таблице
                if "error" in analysis:
                    recommendation = f"Ошибка: {analysis['error']}"
                else:
                    safe_to_delete = analysis.get("safe_to_delete", False)
                    explanation = analysis.get("explanation", "Нет объяснения")
                    
                    if safe_to_delete:
                        recommendation = f"✅ Безопасно удалить: {explanation}"
                    else:
                        recommendation = f"❌ Не рекомендуется удалять: {explanation}"
                
                # Обновляем отображение в таблице
                recommendation_item = self.results_table.item(row, 3)
                if recommendation_item:
                    recommendation_item.setText(recommendation)
                else:
                    recommendation_item = QTableWidgetItem(recommendation)
                    self.results_table.setItem(row, 3, recommendation_item)
            
            self.status_label.setText("Анализ завершен")
            self.status_icon.setText("✅")
            self.status_icon.setStyleSheet("font-size: 16px; color: #28a745; min-width: 24px;")
            self.progress_label.hide()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Произошла ошибка при анализе папок: {e}")
            self.status_label.setText("Ошибка при анализе")
            self.status_icon.setText("⚠")
            self.status_icon.setStyleSheet("font-size: 16px; color: #dc3545; min-width: 24px;")
            self.progress_label.hide()
        
        # Сбрасываем текущую обрабатываемую строку
        self.current_row = -1
        self.analyze_button.setEnabled(True)


# Функция для вызова диалога AI ассистента
def show_ai_assistant_dialog(parent, folders_list):
    """Показывает диалоговое окно AI ассистента для анализа папок."""
    dialog = AIAssistantDialog(parent, folders_list)
    return dialog.exec_()