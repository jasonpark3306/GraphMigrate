import sys
from PyQt6.QtWidgets import QApplication
from main import GraphMigrate

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = GraphMigrate()
    viewer.show()
    sys.exit(app.exec())
