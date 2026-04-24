from PyQt5.QtWidgets import *
from PyQt5.QtCore import QThread, pyqtSignal

from utils.storage import load_file
from utils.progress import ProgressTracker
from memory import save_history

from agents.planner_agent import extract_items
from agents.comparison_agent import compare_prices

from automation.blinkit_bot import BlinkitBot
from automation.zepto_bot import ZeptoBot


class Worker(QThread):
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(dict)

    def __init__(self, prompt, file_data):
        super().__init__()
        self.prompt = prompt
        self.file_data = file_data

    def run(self):
        tracker = ProgressTracker(self.progress_signal.emit)

        # ---------------- PARSE INPUT ----------------
        tracker.update(5, "Parsing input...")

        parsed = extract_items(self.prompt)

        items = []
        for name in parsed["priority_items"]:
            q = parsed["item_quantities"].get(
                name, {"amount": 1, "unit": "unit"}
            )

            items.append({
                "name": name,
                "amount": q["amount"],
                "unit": q["unit"]
            })

        if self.file_data:
            save_history(self.file_data)

        # ---------------- BLINKIT ----------------
        tracker.update(10, "Running Blinkit...")

        blinkit = BlinkitBot()
        blinkit_cart = blinkit.run(items, tracker)

        # ---------------- ZEPTO ----------------
        tracker.update(10, "Running Zepto...")

        zepto_items = []
        for b in blinkit_cart:
            zepto_items.append({
                "name": b["name"]
            })

        zepto = ZeptoBot()
        zepto_cart = zepto.run(zepto_items, tracker)

        # ---------------- COMPARE ----------------
        tracker.update(10, "Comparing prices...")

        result = compare_prices(blinkit_cart, zepto_cart)

        self.result_signal.emit(result)


class App(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("AI Shopping Assistant")
        self.setGeometry(200, 200, 900, 600)

        main_layout = QVBoxLayout()

        # ---------------- TOP INPUT ----------------
        top_layout = QVBoxLayout()

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText(
            "Enter items (e.g., milk and eggs / chicken biriyani)"
        )
        self.input_box.setFixedHeight(80)

        btn_layout = QHBoxLayout()

        self.upload_btn = QPushButton("Upload History")
        self.upload_btn.clicked.connect(self.upload_file)

        self.start_btn = QPushButton("Start Shopping")
        self.start_btn.clicked.connect(self.start_process)

        btn_layout.addWidget(self.upload_btn)
        btn_layout.addWidget(self.start_btn)

        top_layout.addWidget(self.input_box)
        top_layout.addLayout(btn_layout)

        # ---------------- BOTTOM SPLIT ----------------
        bottom_layout = QHBoxLayout()

        # LEFT (70%) → Logs + Progress
        left_layout = QVBoxLayout()

        self.progress = QProgressBar()
        left_layout.addWidget(self.progress)

        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        left_layout.addWidget(self.logs)

        left_container = QWidget()
        left_container.setLayout(left_layout)

        # RIGHT (30%) → Price Table
        right_layout = QVBoxLayout()

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Item", "Blinkit ₹", "Zepto ₹"])
        self.table.horizontalHeader().setStretchLastSection(True)

        right_layout.addWidget(QLabel("Price Comparison"))
        right_layout.addWidget(self.table)

        right_container = QWidget()
        right_container.setLayout(right_layout)

        bottom_layout.addWidget(left_container, 7)
        bottom_layout.addWidget(right_container, 3)

        main_layout.addLayout(top_layout)
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

        self.file_data = None

    # ---------------- FILE UPLOAD ----------------
    def upload_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Upload File")
        if file:
            self.file_data = load_file(file)
            self.logs.append("History loaded")

    # ---------------- PROGRESS ----------------
    def update_progress(self, val, msg):
        self.progress.setValue(val)
        self.logs.append(msg)

    # ---------------- RESULT ----------------
    def show_result(self, result):
        items = result["items"]

        self.table.setRowCount(len(items))

        for i, item in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(item["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(str(item["blinkit"])))
            self.table.setItem(i, 2, QTableWidgetItem(str(item["zepto"])))

        summary = f"\nTotal Blinkit: ₹{result['blinkit_total']}\n"
        summary += f"Total Zepto: ₹{result['zepto_total']}\n"
        summary += f"Saved: ₹{result['savings']} ({result['cheaper']})\n"

        self.logs.append(summary)

        QMessageBox.information(
            self,
            "Savings Summary",
            f"You saved ₹{result['savings']} using {result['cheaper']}"
        )

    # ---------------- START ----------------
    def start_process(self):
        prompt = self.input_box.toPlainText().strip()

        if not prompt:
            self.logs.append("Please enter items.")
            return

        self.worker = Worker(prompt, self.file_data)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.result_signal.connect(self.show_result)

        self.worker.start()