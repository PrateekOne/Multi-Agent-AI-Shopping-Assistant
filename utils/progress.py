# progress.py
class ProgressTracker:
    def __init__(self, callback):
        self.callback = callback
        self.value = 0

    def update(self, step=5, msg=""):
        self.value += step
        if self.value > 100:
            self.value = 100
        self.callback(self.value, msg)
