from PyQt5.QtWidgets import QDialog
from .dialog import Ui_BatTransectsDialog

class BatTransectsDialog(QDialog, Ui_BatTransectsDialog):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
