from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, 
                            QPushButton, QHBoxLayout, QWidget)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPalette, QColor

class DisclaimerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отказ от ответственности")
        self.setMinimumWidth(600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Заголовок
        title = QLabel("Отказ от ответственности и условия использования")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Текст отказа от ответственности
        disclaimer_text = (
            "ВНИМАНИЕ: Настоящее программное обеспечение (далее — «ПО») предоставляется автором на условиях «как есть» (as is), "
            "без каких-либо явных, подразумеваемых или предполагаемых гарантий, включая, но не ограничиваясь, гарантией "
            "пригодности для конкретной цели, соответствия ожиданиям пользователя, непрерывности работы или отсутствия ошибок.\n\n"

            "ПО разработано исключительно для целей интеллектуального анализа и очистки дискового пространства. Пользователь "
            "осознаёт и принимает, что использование ПО осуществляется на его собственный риск.\n\n"

            "Автор (разработчик) не несёт и не может нести ответственности за какой-либо прямой, косвенный, случайный, особый, "
            "штрафной или сопутствующий ущерб, включая, но не ограничиваясь, утратой данных, повреждением программного или "
            "аппаратного обеспечения, сбоями в работе оборудования, перерывами в бизнесе или любыми иными последствиями, возникшими "
            "в связи с использованием или невозможностью использования данного ПО, даже если автор был уведомлён о возможности "
            "такого ущерба.\n\n"

            "Устанавливая и/или используя данное ПО, пользователь подтверждает своё согласие с условиями настоящего отказа от ответственности."
        )
        
        disclaimer_label = QLabel(disclaimer_text)
        disclaimer_label.setWordWrap(True)
        disclaimer_label.setAlignment(Qt.AlignJustify)
        disclaimer_label.setStyleSheet("QLabel { background-color: #f8f9fa; padding: 20px; border-radius: 5px; }")
        layout.addWidget(disclaimer_label)
        
        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        accept_button = QPushButton("Принять")
        accept_button.setMinimumWidth(120)
        accept_button.setStyleSheet("""
            QPushButton {
                background-color: #4a6fa5;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #6b8cae;
            }
        """)
        accept_button.clicked.connect(self.accept)
        
        exit_button = QPushButton("Выход")
        exit_button.setMinimumWidth(120)
        exit_button.setStyleSheet("""
            QPushButton {
                background-color: #e63946;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c1121f;
            }
        """)
        exit_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(accept_button)
        button_layout.addWidget(exit_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout) 