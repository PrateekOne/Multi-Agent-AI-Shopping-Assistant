import logging

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from agents.comparison_agent import compare_prices
from agents.planner_agent import extract_items
from automation.blinkit_bot import BlinkitBot
from automation.zepto_bot import ZeptoBot
from memory import disable_preferences, enable_preferences, save_history
from utils.playwright_manager import close_all_pages
from utils.progress import ProgressTracker
from utils.storage import load_file

logger = logging.getLogger(__name__)


DARK_STYLE = """
QWidget {
    background-color: #0f1117;
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
    font-size: 13px;
}
QFrame#card {
    background-color: #1a1f2e;
    border: 1px solid #2d3548;
    border-radius: 12px;
    padding: 4px;
}
QTextEdit#inputBox {
    background-color: #1a1f2e;
    color: #e2e8f0;
    border: 1px solid #3a4258;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    selection-background-color: #4f6ef7;
}
QTextEdit#inputBox:focus {
    border: 1px solid #4f6ef7;
}
QTextEdit#logBox {
    background-color: #12151f;
    color: #94a3b8;
    border: 1px solid #1e2435;
    border-radius: 8px;
    padding: 10px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
QPushButton#primaryBtn {
    background-color: #4f6ef7;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
    min-height: 38px;
}
QPushButton#primaryBtn:hover  { background-color: #6b85f8; }
QPushButton#primaryBtn:pressed { background-color: #3b57d6; }
QPushButton#primaryBtn:disabled {
    background-color: #2d3548;
    color: #4a5568;
}
QPushButton#secondaryBtn {
    background-color: transparent;
    color: #94a3b8;
    border: 1px solid #2d3548;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    min-height: 38px;
}
QPushButton#secondaryBtn:hover {
    background-color: #1a1f2e;
    color: #e2e8f0;
    border-color: #4f6ef7;
}
QProgressBar {
    background-color: #1a1f2e;
    border: none;
    border-radius: 5px;
    height: 8px;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f6ef7, stop:1 #7c3aed);
    border-radius: 5px;
}
QTableWidget {
    background-color: #12151f;
    border: 1px solid #1e2435;
    border-radius: 8px;
    gridline-color: #1e2435;
    color: #e2e8f0;
    selection-background-color: #1e2d5e;
    font-size: 13px;
}
QTableWidget::item {
    padding: 8px 12px;
    border-bottom: 1px solid #1e2435;
}
QTableWidget::item:selected { background-color: #1e2d5e; color: #e2e8f0; }
QHeaderView::section {
    background-color: #1a1f2e;
    color: #64748b;
    border: none;
    border-bottom: 1px solid #2d3548;
    padding: 8px 12px;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
}
QScrollBar:vertical {
    background: #12151f;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2d3548;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #4f6ef7; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QLabel#sectionTitle {
    color: #64748b;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}
QLabel#savingsBanner {
    background-color: #14291e;
    color: #34d399;
    border: 1px solid #1a4731;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: bold;
}
QLabel#savingsBannerNeutral {
    background-color: #1a1f2e;
    color: #94a3b8;
    border: 1px solid #2d3548;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 13px;
}
QLabel#historyBadge {
    background-color: #14291e;
    color: #34d399;
    border: 1px solid #1a4731;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: bold;
}
QLabel#historyBadgeOff {
    background-color: #1a1f2e;
    color: #4a5568;
    border: 1px solid #2d3548;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
}
"""


class Worker(QThread):
    progress_signal = pyqtSignal(int, str)
    result_signal   = pyqtSignal(dict)
    error_signal    = pyqtSignal(str)
    log_signal      = pyqtSignal(str, str)   # (message, level)

    def __init__(self, prompt: str, history_data, use_preferences: bool):
        super().__init__()
        self.prompt = prompt
        self.history_data = history_data
        self.use_preferences = use_preferences

    def run(self):
        tracker = ProgressTracker(self.progress_signal.emit)

        try:
            # Apply or reset brand preference gate depending on whether
            # the user uploaded history before clicking Start
            if self.history_data:
                save_history(self.history_data)
                enable_preferences()
                self.log_signal.emit("Brand preferences active (history loaded).", "info")
            else:
                disable_preferences()

            tracker.update(5, "Parsing your shopping list...")
            parsed = extract_items(self.prompt)

            items = []
            for name in parsed["priority_items"]:
                q = parsed["item_quantities"].get(name, {"amount": 1, "unit": "unit"})
                items.append({"name": name, "amount": q["amount"], "unit": q["unit"]})

            self.log_signal.emit(
                f"Found {len(items)} item(s): {', '.join(i['name'] for i in items)}", "info"
            )

            # Close any tabs left open from the previous run before launching new ones
            close_all_pages()

            tracker.update(10, "Running Blinkit...")
            blinkit = BlinkitBot()
            blinkit_cart = blinkit.run(items, tracker)

            tracker.update(10, "Running Zepto...")
            zepto = ZeptoBot()
            zepto_cart = zepto.run(items, tracker)

            tracker.update(10, "Comparing prices...")
            result = compare_prices(blinkit_cart, zepto_cart)
            self.result_signal.emit(result)

        except Exception as exc:
            logger.error("Worker failed: %s", exc, exc_info=True)
            self.error_signal.emit(str(exc))


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.file_data = None
        self.worker: Worker | None = None
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("AI Shopping Assistant")
        self.setMinimumSize(1000, 660)
        self.setStyleSheet(DARK_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        root.addLayout(self._header())
        root.addLayout(self._input_panel())
        root.addWidget(self._divider())

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(self._left_panel(), 6)
        body.addLayout(self._right_panel(), 4)
        root.addLayout(body)

    def _header(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        title = QLabel("🛒  AI Shopping Assistant")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet("color: #e2e8f0; background: transparent;")

        self.history_badge = QLabel("No History")
        self.history_badge.setObjectName("historyBadgeOff")
        self.history_badge.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(self.history_badge)
        return layout

    def _input_panel(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        label = QLabel("SHOPPING LIST")
        label.setObjectName("sectionTitle")

        self.input_box = QTextEdit()
        self.input_box.setObjectName("inputBox")
        self.input_box.setPlaceholderText(
            "What do you want to buy?  e.g.  2 litres of milk, eggs and brown bread"
        )
        self.input_box.setFixedHeight(72)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.upload_btn = QPushButton("⬆  Upload History")
        self.upload_btn.setObjectName("secondaryBtn")
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.clicked.connect(self.upload_file)

        self.start_btn = QPushButton("▶  Start Shopping")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_process)

        self.clear_btn = QPushButton("✕  Clear")
        self.clear_btn.setObjectName("secondaryBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.reset_ui)

        btn_row.addWidget(self.upload_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.clear_btn)
        btn_row.addWidget(self.start_btn)

        layout.addWidget(label)
        layout.addWidget(self.input_box)
        layout.addLayout(btn_row)
        return layout

    def _left_panel(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        label = QLabel("ACTIVITY LOG")
        label.setObjectName("sectionTitle")

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)

        self.savings_label = QLabel("")
        self.savings_label.setObjectName("savingsBannerNeutral")
        self.savings_label.setAlignment(Qt.AlignCenter)
        self.savings_label.setWordWrap(True)
        self.savings_label.hide()

        layout.addWidget(label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_box)
        layout.addWidget(self.savings_label)
        return layout

    def _right_panel(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        label = QLabel("PRICE COMPARISON")
        label.setObjectName("sectionTitle")

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Item", "Blinkit ₹", "Zepto ₹"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(label)
        layout.addWidget(self.table)
        return layout

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #2d3548; background: #2d3548; max-height: 1px;")
        return line

    def upload_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Upload Purchase History", "", "JSON Files (*.json);;All Files (*)"
        )
        if file:
            self.file_data = load_file(file)
            self.history_badge.setObjectName("historyBadge")
            self.history_badge.setText("✓ History Loaded")
            self.history_badge.style().unpolish(self.history_badge)
            self.history_badge.style().polish(self.history_badge)
            self._append_log("Purchase history uploaded — brand preferences active.", "info")

    def update_progress(self, val: int, msg: str):
        current = self.progress_bar.value()
        self.progress_bar.setValue(max(current, min(current + val, 95)))
        if msg:
            self._append_log(msg, "info")

    def handle_log(self, msg: str, level: str):
        self._append_log(msg, level)

    def show_result(self, result: dict):
        self.progress_bar.setValue(100)

        items = result.get("items", [])
        self.table.setRowCount(len(items))

        for i, item in enumerate(items):
            b_price = item.get("blinkit", "-")
            z_price = item.get("zepto", "-")

            name_cell  = QTableWidgetItem(item.get("name", ""))
            b_cell     = QTableWidgetItem(f"₹{b_price}" if b_price != "-" else "-")
            z_cell     = QTableWidgetItem(f"₹{z_price}" if z_price != "-" else "-")

            for cell in (name_cell, b_cell, z_cell):
                cell.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

            self.table.setItem(i, 0, name_cell)
            self.table.setItem(i, 1, b_cell)
            self.table.setItem(i, 2, z_cell)

        savings = result.get("savings", 0)
        cheaper = result.get("cheaper", "")
        b_total = result.get("blinkit_total", 0)
        z_total = result.get("zepto_total", 0)

        if savings > 0 and cheaper:
            self.savings_label.setObjectName("savingsBanner")
            self.savings_label.setText(
                f"💰  Save ₹{savings} — {cheaper} is cheaper   "
                f"(Blinkit ₹{b_total}  ·  Zepto ₹{z_total})"
            )
        else:
            self.savings_label.setObjectName("savingsBannerNeutral")
            self.savings_label.setText(
                f"Prices are equal   (Blinkit ₹{b_total}  ·  Zepto ₹{z_total})"
            )

        self.savings_label.style().unpolish(self.savings_label)
        self.savings_label.style().polish(self.savings_label)
        self.savings_label.show()

        self._append_log(
            f"Done — Blinkit ₹{b_total}  |  Zepto ₹{z_total}  |  Save ₹{savings} with {cheaper}",
            "success",
        )
        self._set_running(False)

    def show_error(self, msg: str):
        self._append_log(f"ERROR: {msg}", "error")
        self._set_running(False)

    def reset_ui(self):
        # Clear results so the user can run a completely new search
        self.input_box.clear()
        self.log_box.clear()
        self.table.setRowCount(0)
        self.savings_label.hide()
        self.progress_bar.setValue(0)

    def start_process(self):
        prompt = self.input_box.toPlainText().strip()
        if not prompt:
            self._append_log("Please enter items before starting.", "warning")
            return

        # Properly terminate any previous worker thread before creating a new one.
        # Without this, the second run fires signals twice and can cause crashes.
        if self.worker is not None and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(3000)

        self.log_box.clear()
        self.table.setRowCount(0)
        self.savings_label.hide()
        self.progress_bar.setValue(0)
        self._set_running(True)
        self._append_log(f'Starting search: "{prompt}"', "info")

        self.worker = Worker(
            prompt=prompt,
            history_data=self.file_data,
            use_preferences=self.file_data is not None,
        )
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.result_signal.connect(self.show_result)
        self.worker.error_signal.connect(self.show_error)
        self.worker.log_signal.connect(self.handle_log)
        self.worker.start()

    def _set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.upload_btn.setEnabled(not running)
        self.start_btn.setText("⏳  Running..." if running else "▶  Start Shopping")

    def _append_log(self, msg: str, level: str = "info"):
        colour = {"info": "#94a3b8", "success": "#34d399", "warning": "#f59e0b", "error": "#f87171"}.get(level, "#94a3b8")
        prefix = {"info": "·", "success": "✓", "warning": "⚠", "error": "✕"}.get(level, "·")
        self.log_box.append(f'<span style="color:{colour};">{prefix}  {msg}</span>')
