# Standard library imports
import sys
import os
import configparser
import csv
import urllib.parse
import logging
from datetime import datetime, timedelta
import time

# Third-party library imports
import psycopg2
from neo4j import GraphDatabase
import neo4j.exceptions
import pymongo
import pandas as pd
import networkx as nx

# PyQt6 imports
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QComboBox, QTableWidget, 
    QVBoxLayout, QHBoxLayout, QWidget, QTextEdit, 
    QLabel, QStatusBar, QMenuBar, QMenu, QTableWidgetItem,
    QHeaderView, QPushButton, QFileDialog, QMessageBox,
    QPlainTextEdit, QDialog, QSizePolicy, QTabWidget,
    QProgressDialog, QGridLayout, QLineEdit, QCheckBox, QProgressBar
)
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import (
    QAction, QColor, QBrush, QFont, QTextCharFormat, QSyntaxHighlighter
)
from PyQt6.QtCore import (
    Qt, QRegularExpression, QRect, QSize, QThread, pyqtSignal
)

from PyQt6.QtGui import QColor, QTextCharFormat, QFont, QSyntaxHighlighter
from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QColor, QTextCharFormat, QFont, QSyntaxHighlighter, QPalette
from PyQt6.QtCore import QRegularExpression, Qt

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas


class DraggableGraph:
    def __init__(self, fig, ax, G, pos, click_callback):
        self.fig = fig
        self.ax = ax
        self.G = G
        self.pos = pos
        self.click_callback = click_callback
        self.dragged_node = None
        self.nodes = nx.draw_networkx_nodes(G, pos, ax=ax, node_size=3000)
        self.edges = nx.draw_networkx_edges(G, pos, ax=ax, arrows=True, arrowsize=20, edge_color='gray', width=1.5)
        self.labels = nx.draw_networkx_labels(G, pos, ax=ax, 
                                              labels={node: f"{data['label']}\n{data['name']}" for node, data in G.nodes(data=True)},
                                              font_size=8, font_weight='bold')
        
        self.nodes.set_picker(True)
        self.nodes.set_pickradius(20)
        
        self.fig.canvas.mpl_connect('button_press_event', self.on_press)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)

    def on_press(self, event):
        if event.inaxes != self.ax:
            return
        cont, ind = self.nodes.contains(event)
        if cont:
            self.dragged_node = ind['ind'][0]
            if event.button == 1:  # Left click
                self.click_callback(list(self.G.nodes())[self.dragged_node])

    def on_motion(self, event):
        if self.dragged_node is not None and event.inaxes == self.ax:
            node = list(self.G.nodes())[self.dragged_node]
            self.pos[node] = (event.xdata, event.ydata)
            self.update()

    def on_release(self, event):
        self.dragged_node = None

    def update(self):
        self.nodes.set_offsets([self.pos[node] for node in self.G.nodes()])
        self.edges.set_positions(self.pos)
        for node, (x, y) in self.pos.items():
            self.labels[node].set_position((x, y))
        self.fig.canvas.draw_idle()

        
class CypherHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = ["MATCH", "WHERE", "CREATE", "RETURN", "AS"]
        for word in keywords:
            pattern = QRegularExpression(r'\b' + word + r'\b')
            self.highlighting_rules.append((pattern, keyword_format))

        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#DCDCAA"))
        function_pattern = QRegularExpression(r'\b[A-Za-z0-9_]+(?=\()')
        self.highlighting_rules.append((function_pattern, function_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))
        string_pattern = QRegularExpression(r'`[^`]*`')
        self.highlighting_rules.append((string_pattern, string_format))

        variable_format = QTextCharFormat()
        variable_format.setForeground(QColor("#9CDCFE"))
        variable_pattern = QRegularExpression(r'\b[a-z_]\w*\b')
        self.highlighting_rules.append((variable_pattern, variable_format))

        # Change relationship color to green and make it bold
        self.relationship_format = QTextCharFormat()
        self.relationship_format.setForeground(QColor("green"))
        self.relationship_format.setFontWeight(QFont.Weight.Bold)

        # Keep property color as blue
        self.property_format = QTextCharFormat()
        self.property_format.setForeground(QColor("blue"))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            expression = QRegularExpression(pattern)
            it = expression.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

        # Highlight relationship name (green and bold)
        rel_pattern = QRegularExpression(r':`(\w+)`')
        it = rel_pattern.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(match.capturedStart(1), match.capturedLength(1), self.relationship_format)

        # Highlight properties (blue)
        prop_pattern = QRegularExpression(r'\.`(\w+)`')
        it = prop_pattern.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(match.capturedStart(1), match.capturedLength(1), self.property_format)
            

class MigrationWorker(QThread):
    progress = pyqtSignal(int, int)
    log = pyqtSignal(str, str, str)  # category, message, level
    finished = pyqtSignal()

    def __init__(self, parent, source_db, target_db, source_table, target_table, source_columns, target_columns):
        super().__init__(parent)
        self.parent = parent
        self.source_db = source_db
        self.target_db = target_db
        self.source_table = source_table
        self.target_table = target_table
        self.source_columns = source_columns
        self.target_columns = target_columns
        self.total_rows = 0
        self.migrated_rows = 0
        self.error_message = ""

    def run(self):
        try:
            self.log.emit("Migration", f"Fetching data from {self.source_db}.{self.source_table}", "INFO")
            source_data = self.parent.get_data(self.source_db, self.source_table, self.source_columns)
            self.total_rows = len(source_data)
            
            self.log.emit("Migration", f"Starting migration of {self.total_rows} rows from {self.source_db} to {self.target_db}", "INFO")

            self.log.emit("Migration", f"Creating target {self.target_db}.{self.target_table}", "INFO")
            self.parent.create_target_table(self.target_db, self.target_table, self.target_columns)

            for i, row in enumerate(source_data):
                try:
                    if isinstance(row, dict):
                        target_row = {target_col: row.get(source_col) for source_col, target_col in zip(self.source_columns, self.target_columns)}
                    else:
                        target_row = dict(zip(self.target_columns, row))
                    
                    self.parent.insert_row(self.target_db, self.target_table, self.target_columns, target_row)
                    self.migrated_rows += 1
                except Exception as e:
                    self.log.emit("Migration", f"Error migrating row {i+1}: {str(e)}", "ERROR")

                self.progress.emit(i + 1, self.total_rows)
                if (i + 1) % 100 == 0 or i + 1 == self.total_rows:
                    self.log.emit("Migration", f"Migrated {i + 1}/{self.total_rows} rows", "INFO")

            self.log.emit("Migration", f"Migration from {self.source_db} to {self.target_db} completed successfully", "INFO")
        except Exception as e:
            self.error_message = str(e)
            self.log.emit("Migration", f"Error during migration: {self.error_message}", "ERROR")
        finally:
            self.finished.emit()



class CsvViewerDialog(QDialog):
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"CSV Viewer - {os.path.basename(self.file_path)}")
        self.setGeometry(200, 200, 1000, 700)

        layout = QVBoxLayout()

        # File info
        file_size = os.path.getsize(self.file_path)
        file_info = f"File: {os.path.basename(self.file_path)} | Size: {file_size} bytes"
        info_label = QLabel(file_info)
        layout.addWidget(info_label)

        # Text editor
        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Courier New", 10)
        self.editor.setFont(font)
        layout.addWidget(self.editor)

        # Load content
        with open(self.file_path, 'r', encoding='utf-8-sig') as file:
            content = file.read()
        self.editor.setPlainText(content)

        # Apply syntax highlighting
        self.highlighter = CsvHighlighter(self.editor.document())

        self.editor.setReadOnly(True)

        self.setLayout(layout)

class CsvHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlight_rules = []

        # Define a list of colors for columns
        self.column_colors = [
            QColor("#FFB3BA"),  # Light Pink
            QColor("#BAFFC9"),  # Light Green
            QColor("#BAE1FF"),  # Light Blue
            QColor("#FFFFBA"),  # Light Yellow
            QColor("#FFD8B3"),  # Light Orange
            QColor("#E0B3FF"),  # Light Purple
            QColor("#B3FFF6"),  # Light Cyan
            QColor("#FFC8B3"),  # Light Coral
        ]

        # Highlight header (first line)
        header_format = QTextCharFormat()
        header_format.setFontWeight(QFont.Weight.Bold)
        header_format.setBackground(QColor("#E0E0E0"))  # Light Gray background
        self.highlight_rules.append(("^.+$", header_format, 0))

    def highlightBlock(self, text):
        # First, apply header highlighting
        for pattern, format, _ in self.highlight_rules:
            expression = QRegularExpression(pattern)
            match = expression.match(text)
            if match.hasMatch():
                start = match.capturedStart()
                length = match.capturedLength()
                self.setFormat(start, length, format)

        # Then, apply column-based coloring
        if self.currentBlock().blockNumber() > 0:  # Skip the header row
            columns = text.split(',')
            start_index = 0
            for i, column in enumerate(columns):
                color = self.column_colors[i % len(self.column_colors)]
                format = QTextCharFormat()
                format.setBackground(color)
                self.setFormat(start_index, len(column), format)
                start_index += len(column) + 1  # +1 for the comma



class DbConfigEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("db.ini Editor")
        self.config = configparser.ConfigParser()
        self.config.read('db.ini')
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # Create layouts for each database
        for section in ['postgresql', 'neo4j', 'mongodb']:
            group_layout = QGridLayout()
            section_label = QLabel(section.capitalize())
            section_label.setStyleSheet("font-weight: normal;")
            group_layout.addWidget(section_label, 0, 0, 1, 2)
            setattr(self, f"{section}_label", section_label)
            
            for row, (key, value) in enumerate(self.config[section].items(), start=1):
                label = QLabel(f"{key}:")
                label.setStyleSheet("color: black;")
                group_layout.addWidget(label, row, 0)
                
                line_edit = QLineEdit(value)
                group_layout.addWidget(line_edit, row, 1)
                setattr(self, f"{section}_{key}_edit", line_edit)

            test_button = QPushButton(f"Test {section.capitalize()} Connection")
            test_button.clicked.connect(lambda checked, s=section: self.test_connection(s))
            group_layout.addWidget(test_button, row+1, 0, 1, 2)

            main_layout.addLayout(group_layout)

        # Log message box
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.log_text.setMaximumHeight(100)  # Set maximum height to 100 pixels
        main_layout.addWidget(self.log_text)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')

        save_action = QAction('Save', self)
        save_action.triggered.connect(self.save_config)
        file_menu.addAction(save_action)

        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Set window size
        self.resize(self.sizeHint().width() * 2, self.sizeHint().height())
        

    def save_config(self):
        for section in ['postgresql', 'neo4j', 'mongodb']:
            for key in self.config[section]:
                value = getattr(self, f"{section}_{key}_edit").text()
                self.config[section][key] = value

        with open('db.ini', 'w') as configfile:
            self.config.write(configfile)

    def test_connection(self, db_type):
        self.save_config()
        try:
            if db_type == 'postgresql':
                conn = psycopg2.connect(
                    host=self.config['postgresql']['host'],
                    port=self.config['postgresql']['port'],
                    database=self.config['postgresql']['database'],
                    user=self.config['postgresql']['user'],
                    password=self.config['postgresql']['password']
                )
                conn.close()
            elif db_type == 'neo4j':
                driver = GraphDatabase.driver(
                    self.config['neo4j']['url'],
                    auth=(self.config['neo4j']['user'], self.config['neo4j']['password'])
                )
                with driver.session() as session:
                    session.run("RETURN 1")
                driver.close()
            elif db_type == 'mongodb':
                if self.config['mongodb']['host'] == 'localhost' or self.config['mongodb']['host'].startswith('127.0.0.1'):
                    mongodb_url = f"mongodb://{self.config['mongodb']['host']}:{self.config['mongodb']['port']}/{self.config['mongodb']['database']}"
                else:
                    mongodb_url = f"mongodb+srv://{self.config['mongodb']['user']}:{urllib.parse.quote_plus(self.config['mongodb']['password'])}@{self.config['mongodb']['host']}/{self.config['mongodb']['database']}?retryWrites=true&w=majority"
                client = pymongo.MongoClient(mongodb_url)
                client.server_info()
                client.close()

            self.log_message(f"{db_type.capitalize()} connection successful!", "green")
            getattr(self, f"{db_type}_label").setStyleSheet("font-weight: normal; color: green;")
        except Exception as e:
            self.log_message(f"Error connecting to {db_type}: {str(e)}", "red")
            getattr(self, f"{db_type}_label").setStyleSheet("font-weight: normal; color: red;")
            


    def log_message(self, message, color):
        self.log_text.append(f'<font color="{color}">{message}</font>')

    def closeEvent(self, event):
        event.accept()    

        # reply = QMessageBox.question(self, 'Exit', 'Are you sure you want to exit?',
        #                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        # if reply == QMessageBox.StandardButton.Yes:
        #     event.accept()
        # else:
        #     event.ignore()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = DbConfigEditor()
    editor.show()
    sys.exit(app.exec())


class MigrationReport(QDialog):
    def __init__(self, report_data):
        super().__init__()
        self.report_data = report_data
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Migration Report")
        self.setGeometry(100, 100, 800, 600)

        layout = QVBoxLayout()

        # Create table widget
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Item", "Records", "Result", "Migrated", "Failed", "Time", "Error"
        ])
        self.populate_table()

        layout.addWidget(self.table)

        # Add download button
        download_btn = QPushButton("Download Report")
        download_btn.clicked.connect(self.download_report)
        layout.addWidget(download_btn)

        self.setLayout(layout)

    def populate_table(self):
        self.table.setRowCount(len(self.report_data['items']))
        for i, item in enumerate(self.report_data['items']):
            self.table.setItem(i, 0, QTableWidgetItem(item['name']))
            self.table.setItem(i, 1, QTableWidgetItem(str(item['records'])))
            self.table.setItem(i, 2, QTableWidgetItem(item['result']))
            self.table.setItem(i, 3, QTableWidgetItem(str(item['migrated'])))
            self.table.setItem(i, 4, QTableWidgetItem(str(item['failed'])))
            self.table.setItem(i, 5, QTableWidgetItem(str(timedelta(seconds=item['time']))))
            self.table.setItem(i, 6, QTableWidgetItem(item['error']))

        self.table.resizeColumnsToContents()

    def download_report(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Report", "migration_report.csv", "CSV Files (*.csv)")
        if file_name:
            with open(file_name, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Migration Report"])
                writer.writerow([f"Total Items: {self.report_data['total_items']}"])
                writer.writerow([f"Total Time: {timedelta(seconds=self.report_data['total_time'])}"])
                writer.writerow([])
                writer.writerow(["Item", "Records", "Result", "Migrated", "Failed", "Time", "Error"])
                for item in self.report_data['items']:
                    writer.writerow([
                        item['name'], item['records'], item['result'], 
                        item['migrated'], item['failed'], 
                        str(timedelta(seconds=item['time'])), item['error']
                    ])