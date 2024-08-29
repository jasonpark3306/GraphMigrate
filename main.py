# Standard library imports
import sys
import os
import configparser
import csv
import urllib.parse
import logging
from datetime import date, datetime, timedelta
import locale
import time
from decimal import Decimal

# Third-party library imports
import psycopg2
from neo4j import GraphDatabase
import neo4j.exceptions
import pymongo
import pandas as pd
import networkx as nx
import pytz
from neo4j.time import DateTime, Date

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QComboBox, QTableWidget, 
    QVBoxLayout, QHBoxLayout, QWidget, QTextEdit, 
    QLabel, QStatusBar, QMenuBar, QMenu, QTableWidgetItem,
    QHeaderView, QPushButton, QFileDialog, QMessageBox,
    QPlainTextEdit, QDialog, QSizePolicy, QTabWidget,
    QProgressDialog, QGridLayout, QLineEdit, QCheckBox, QProgressBar,
    QListWidget, QListWidgetItem
)
from PyQt6.QtGui import (
    QAction, QColor, QBrush, QFont, QTextCharFormat, QSyntaxHighlighter, QPalette
)
from PyQt6.QtCore import (
    Qt, QRegularExpression, QRect, QSize, QThread, pyqtSignal
)
import os
os.environ['QT_API'] = 'pyqt6'

import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

# Local imports
from util import DraggableGraph, CypherHighlighter, DbConfigEditor, MigrationReport, MigrationWorker, CsvHighlighter, CsvViewerDialog
import random

class Migrate(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Graph Migrate 0.5")
        self.setGeometry(100, 100, 1200, 800)

        # Set up logging
        logging.basicConfig(level=logging.INFO, 
                            format='%(asctime)s %(levelname)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

        self.db_info_labels = {}
        self.select_combos = {}
        self.download_csv_btns = {}
        self.view_csv_btns = {}
        self.upload_csv_btns = {}
        self.table_widgets = {}
        self.log_texts = {}
        self.delete_btns = {}
        self.download_multiple_csv_btns = {}
        self.upload_multiple_csv_btns = {}

        self.pg_conn = None
        self.pg_cur = None
        self.neo4j_driver = None
        self.mongo_client = None
        self.mongo_db = None  # Add this line
        self.config = None
        self.worker = None
        
        self.load_config()  # Load config first
        self.init_ui()  # Then initialize UI
        self.connect_to_databases()  # Finally connect to databases

        # Apply default stylesheet
        self.load_and_apply_stylesheet("style_light.ini") 


    def generate_random_color(self):
        return QColor(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

    def load_and_apply_stylesheet(self, style_file):
        config = configparser.ConfigParser()
        style_path = os.path.join('conf', style_file)
        config.read(style_path)
        stylesheet = config['Style']['stylesheet']
        self.setStyleSheet(stylesheet)
        self.log_message("UI", f"Applied stylesheet from {style_file}", "INFO")


    def log_message(self, category, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] {level} - {category}: {message}"
        
        # Print to system out
        print(formatted_message, file=sys.stdout)
        
        # Write to log panel
        if category in self.log_texts:
            self.log_texts[category].append(formatted_message)
        
        # Write to migrate log panel
        if hasattr(self, 'migrate_log_text'):
            self.migrate_log_text.append(formatted_message)
        
        # Write to relate log panel
        if hasattr(self, 'relate_log_text'):
            self.relate_log_text.append(formatted_message)
        
        # Log using logging module (similar to log4j)
        if level == "INFO":
            logging.info(formatted_message)
        elif level == "ERROR":
            logging.error(formatted_message)
        elif level == "WARN":
            logging.warning(formatted_message)
        elif level == "DEBUG":
            logging.debug(formatted_message)

    def init_ui(self):
        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        # Add "Edit/Test Databases" action
        edit_db_action = QAction("Edit/Test Databases", self)
        edit_db_action.triggered.connect(self.open_db_config_editor)
        file_menu.addAction(edit_db_action)

        # Add "Reload All" action
        reload_action = QAction("Reload All", self)
        reload_action.triggered.connect(self.reload_all)
        file_menu.addAction(reload_action) 

        style_menu = file_menu.addMenu("Set Style")  
        # Add style options
        style_options = [
            ("Blue", "style_blue.ini"),
            ("Custom", "style_custom.ini"),
            ("Dark", "style_dark.ini"),
            ("Light", "style_light.ini")
        ]

        for style_name, style_file in style_options:
            style_action = QAction(style_name, self)
            style_action.triggered.connect(lambda checked, sf=style_file: self.load_and_apply_stylesheet(sf))
            style_menu.addAction(style_action)
            
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.log_tab_change)
        main_layout.addWidget(self.tab_widget)

        # PostgreSQL tab
        pg_tab = QWidget()
        self.setup_database_ui(pg_tab, "PostgreSQL")
        self.tab_widget.addTab(pg_tab, "PostgreSQL")

        # MongoDB tab
        mongo_tab = QWidget()
        self.setup_database_ui(mongo_tab, "MongoDB")
        self.tab_widget.addTab(mongo_tab, "MongoDB")

        # Neo4j tab
        neo4j_tab = QWidget()
        self.setup_database_ui(neo4j_tab, "Neo4j")
        self.tab_widget.addTab(neo4j_tab, "Neo4j")

        # Add Migrate tab
        migrate_tab = QWidget()
        self.setup_migrate_tab_ui(migrate_tab)
        self.tab_widget.addTab(migrate_tab, "Migrate")

        # Add Relate tab
        relate_tab = QWidget()
        self.setup_relate_tab_ui(relate_tab)
        self.tab_widget.addTab(relate_tab, "Relate")
        

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def open_db_config_editor(self):
        self.log_message("UI", "Opening database configuration editor", "INFO")
        db_config_editor = DbConfigEditor()
        result = db_config_editor.show()
        if result == QDialog.DialogCode.Accepted:
            self.log_message("UI", "Database configuration updated", "INFO")
            # Reload database configurations or refresh connections if needed
            self.load_config()
            self.connect_to_databases()


    def connect_relate_tab_signals(self):
        self.source_label_combo.currentTextChanged.connect(self.update_source_properties)
        self.target_label_combo.currentTextChanged.connect(self.update_target_properties)
        self.source_props_list.itemSelectionChanged.connect(self.focus_source_property)
        self.target_props_list.itemSelectionChanged.connect(self.focus_target_property)
        self.source_label_combo.currentTextChanged.connect(self.update_cypher_query)
        self.target_label_combo.currentTextChanged.connect(self.update_cypher_query)
        self.source_props_list.itemSelectionChanged.connect(self.update_cypher_query)
        self.target_props_list.itemSelectionChanged.connect(self.update_cypher_query)
        self.relationship_name_combo.currentTextChanged.connect(self.update_cypher_query)
        self.source_props_list.itemSelectionChanged.connect(self.update_source_property_colors)
        self.target_props_list.itemSelectionChanged.connect(self.update_target_property_colors)
        
    def reload_database(self, db_type):
        self.log_message(db_type, f"Reloading {db_type} connection...", "INFO")
        
        try:
            if db_type == "PostgreSQL":
                self.disconnect_postgresql()
                self.connect_postgresql()
                self.load_tables(db_type)
            elif db_type == "MongoDB":
                self.disconnect_mongodb()
                self.connect_mongodb()
                self.load_collections(db_type)
            else:  # Neo4j
                self.disconnect_neo4j()
                self.connect_neo4j()
                self.load_labels(db_type)
            
            self.update_db_info(db_type)
            self.log_message(db_type, f"{db_type} connection reloaded successfully", "INFO")
        except Exception as e:
            self.log_message(db_type, f"Error reloading {db_type} connection: {str(e)}", "ERROR")

        # Reload the current data
        self.load_data(db_type)

    def reload_all(self):
        self.log_message("UI", "Reloading all database connections", "INFO")
        # Disconnect current database connections
        self.disconnect_databases()
        
        # Re-read the db.ini file
        self.load_config()
        
        # Reconnect to databases
        self.connect_to_databases()
        
        # Refresh all tab contents
        self.refresh_postgresql_tab()
        self.refresh_mongodb_tab()
        self.refresh_neo4j_tab()
        
        QMessageBox.information(self, "Reload Complete", "All database connections and tabs have been reloaded.")
        self.log_message("UI", "All database connections and tabs reloaded", "INFO")

    def load_config(self):
        self.config = configparser.ConfigParser()
        try:
            config_path = os.path.join('conf', 'db.ini')
            self.config.read(config_path)
            if not self.config.sections():
                raise ValueError("No sections found in db.ini")
            self.log_message("Config", "Configuration loaded successfully", "INFO")
        except Exception as e:
            self.log_message("Config", f"Error loading configuration: {str(e)}", "ERROR")
            QMessageBox.critical(self, "Configuration Error", f"Error loading configuration: {str(e)}")
            self.config = None

    def connect_to_databases(self):
        self.connect_postgresql()
        self.connect_mongodb()
        self.connect_neo4j()

    def connect_postgresql(self):
        try:
            self.pg_conn = psycopg2.connect(
                host=self.config['postgresql']['host'],
                port=self.config['postgresql']['port'],
                database=self.config['postgresql']['database'],
                user=self.config['postgresql']['user'],
                password=self.config['postgresql']['password'],
                client_encoding='utf8'
            )
            self.pg_cur = self.pg_conn.cursor()
            self.update_db_info("PostgreSQL")
            self.log_message("PostgreSQL", "Connected to PostgreSQL successfully", "INFO")
            self.load_tables("PostgreSQL")
        except Exception as e:
            self.log_message("PostgreSQL", f"Error connecting to PostgreSQL: {str(e)}", "ERROR")

    def connect_mongodb(self):
        try:
            if self.config['mongodb']['host'] == 'localhost' or self.config['mongodb']['host'].startswith('127.0.0.1'):
                # Local connection
                mongodb_url = f"mongodb://{self.config['mongodb']['host']}:{self.config['mongodb']['port']}/{self.config['mongodb']['database']}"
            else:
                # Remote connection
                mongodb_url = f"mongodb+srv://{self.config['mongodb']['user']}:{urllib.parse.quote_plus(self.config['mongodb']['password'])}@{self.config['mongodb']['host']}/{self.config['mongodb']['database']}?retryWrites=true&w=majority"
            self.mongo_client = pymongo.MongoClient(mongodb_url)
            self.mongo_db = self.mongo_client[self.config['mongodb']['database']]
            self.update_db_info("MongoDB")
            self.log_message("MongoDB", "Connected to MongoDB successfully", "INFO")
            self.load_collections("MongoDB")
        except Exception as e:
            self.log_message("MongoDB", f"Error connecting to MongoDB: {str(e)}", "ERROR")


    def connect_neo4j(self):
        try:
            self.neo4j_driver = GraphDatabase.driver(
                self.config['neo4j']['url'],
                auth=(self.config['neo4j']['user'], self.config['neo4j']['password'])
            )
            # Test the connection
            with self.neo4j_driver.session() as session:
                session.run("RETURN 1")
            self.update_db_info("Neo4j")
            self.log_message("Neo4j", "Connected to Neo4j successfully", "INFO")
            self.load_labels("Neo4j")
        except Exception as e:
            self.neo4j_driver = None  # Ensure driver is set to None on failure
            error_message = f"Error connecting to Neo4j: {str(e)}"
            self.log_message("Neo4j", error_message, "ERROR")

    def log_tab_change(self, index):
        tab_name = self.tab_widget.tabText(index)
        self.log_message("UI", f"Switched to {tab_name} tab", "INFO")
        if tab_name == "Relate":
            self.check_neo4j_connection()
            self.refresh_relationship_types()  # Add this line
            

    def disconnect_postgresql(self):
        if self.pg_conn:
            self.pg_conn.close()
            self.pg_conn = None
            self.pg_cur = None
            self.log_message("PostgreSQL", "Disconnected from PostgreSQL", "INFO")

    def disconnect_mongodb(self):
        if self.mongo_client:
            self.mongo_client.close()
            self.mongo_client = None
            self.mongo_db = None
            self.log_message("MongoDB", "Disconnected from MongoDB", "INFO")

    def disconnect_neo4j(self):
        if self.neo4j_driver:
            self.neo4j_driver.close()
            self.neo4j_driver = None
            self.log_message("Neo4j", "Disconnected from Neo4j", "INFO")

    def disconnect_databases(self):
        self.disconnect_postgresql()
        self.disconnect_mongodb()
        self.disconnect_neo4j()

    def delete_item(self, db_type):
        selected_item = self.select_combos[db_type].currentText()
        if not selected_item:
            self.log_message(db_type, "No item selected for deletion", "WARN")
            return

        try:
            if db_type.lower() == "postgresql":
                self.delete_postgresql_table(selected_item)
            elif db_type.lower() == "mongodb":
                self.delete_mongodb_collection(selected_item)
            else:  # Neo4j
                self.delete_neo4j_label(selected_item)

            self.log_message(db_type, f"Deleted {selected_item}", "INFO")

            # Clear the table widget
            self.table_widgets[db_type].setRowCount(0)
            self.table_widgets[db_type].setColumnCount(0)
            
            # Refresh the combo box
            if db_type.lower() == "postgresql":
                self.load_tables(db_type)
            elif db_type.lower() == "mongodb":
                self.load_collections(db_type)
            else:  # Neo4j
                self.load_labels(db_type)

        except Exception as e:
            self.log_message(db_type, f"Error deleting {selected_item}: {str(e)}", "ERROR")

    def delete_postgresql_table(self, table_name):
        self.pg_cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
        self.pg_conn.commit()

    def delete_mongodb_collection(self, collection_name):
        self.mongo_db[collection_name].drop()

    def delete_neo4j_label(self, label):
        with self.neo4j_driver.session() as session:
            session.run(f"MATCH (n:`{label}`) DETACH DELETE n")

    def refresh_postgresql_tab(self):
        try:
            self.load_tables("PostgreSQL")
            selected_table = self.select_combos["PostgreSQL"].currentText()
            if selected_table:
                self.load_postgresql_data(selected_table)
            self.log_message("PostgreSQL", "PostgreSQL tab refreshed successfully", "INFO")
        except Exception as e:
            self.log_message("PostgreSQL", f"Error refreshing PostgreSQL tab: {str(e)}", "ERROR")

    def refresh_mongodb_tab(self):
        try:
            self.load_collections("MongoDB")
            selected_collection = self.select_combos["MongoDB"].currentText()
            if selected_collection:
                self.load_mongodb_data(selected_collection)
            self.log_message("MongoDB", "MongoDB tab refreshed successfully", "INFO")
        except Exception as e:
            self.log_message("MongoDB", f"Error refreshing MongoDB tab: {str(e)}", "ERROR")

    def refresh_neo4j_tab(self):
        try:
            self.load_labels("Neo4j")
            selected_label = self.select_combos["Neo4j"].currentText()
            if selected_label:
                self.load_neo4j_data(selected_label)
            self.log_message("Neo4j", "Neo4j tab refreshed successfully", "INFO")
        except Exception as e:
            self.log_message("Neo4j", f"Error refreshing Neo4j tab: {str(e)}", "ERROR")

    def update_db_info(self, db_type):
        if db_type == "PostgreSQL":
            if self.pg_conn:
                info = f"Database: {self.config['postgresql']['database']} on {self.config['postgresql']['host']}:{self.config['postgresql']['port']}\n"
                info += f"User: {self.config['postgresql']['user']} | Password: {'*' * len(self.config['postgresql']['password'])}"
            else:
                info = "Database: Not connected"
        elif db_type == "MongoDB":
            if self.mongo_client:
                info = f"Database: {self.config['mongodb']['database']} on {self.config['mongodb']['host']}\n"
                info += f"User: {self.config['mongodb']['user']} | Password: {'*' * len(self.config['mongodb']['password'])}"
            else:
                info = "Database: Not connected"
        elif db_type == "Neo4j":
            if self.neo4j_driver:
                info = f"Database: Neo4j on {self.config['neo4j']['url']}\n"
                info += f"User: {self.config['neo4j']['user']} | Password: {'*' * len(self.config['neo4j']['password'])}"
            else:
                info = "Database: Not connected"
        else:
            info = "Database: Unknown type"
        
        self.db_info_labels[db_type].setText(info)

    def setup_database_ui(self, parent, db_type):
        layout = QVBoxLayout()

        # Database info and reload button
        db_info_layout = QHBoxLayout()
        self.db_info_labels[db_type] = QLabel(f"Database: Not connected")
        db_info_layout.addWidget(self.db_info_labels[db_type])
        
        reload_btn = QPushButton("⟳")  # Unicode symbol for reload
        reload_btn.setFixedSize(self.db_info_labels[db_type].sizeHint().height(), 
                                self.db_info_labels[db_type].sizeHint().height())
        reload_btn.clicked.connect(lambda: self.reload_database(db_type))
        reload_btn.clicked.connect(lambda: self.log_message("UI", f"Reload button clicked for {db_type}", "INFO"))
        db_info_layout.addWidget(reload_btn)
        
        layout.addLayout(db_info_layout)

        # Table/Collection/Label selection and CSV buttons
        select_layout = QHBoxLayout()
        if db_type == "PostgreSQL":
            select_label = "Select Table:"
        elif db_type == "MongoDB":
            select_label = "Select Collection:"
        else:  # Neo4j
            select_label = "Select Label:"
        select_layout.addWidget(QLabel(select_label))

        self.select_combos[db_type] = QComboBox()
        self.select_combos[db_type].currentTextChanged.connect(lambda: self.load_data(db_type))
        select_layout.addWidget(self.select_combos[db_type])

        self.delete_btns[db_type] = QPushButton("Delete")
        self.delete_btns[db_type].clicked.connect(lambda: self.delete_item(db_type))
        self.delete_btns[db_type].clicked.connect(lambda: self.log_message("UI", f"Delete button clicked for {db_type}", "INFO"))
        select_layout.addWidget(self.delete_btns[db_type])
        
        self.download_csv_btns[db_type] = QPushButton("Download CSV")
        self.download_csv_btns[db_type].clicked.connect(lambda: self.download_csv(db_type))
        self.download_csv_btns[db_type].clicked.connect(lambda: self.log_message("UI", f"Download CSV button clicked for {db_type}", "INFO"))
        select_layout.addWidget(self.download_csv_btns[db_type])

        # Add new buttons
        self.download_multiple_csv_btns[db_type] = QPushButton("Download CSVs")
        self.download_multiple_csv_btns[db_type].clicked.connect(lambda: self.download_all(db_type))
        self.download_multiple_csv_btns[db_type].clicked.connect(lambda: self.log_message("UI", f"Download CSVs button clicked for {db_type}", "INFO"))
        select_layout.addWidget(self.download_multiple_csv_btns[db_type])

        self.view_csv_btns[db_type] = QPushButton("View CSV")
        self.view_csv_btns[db_type].clicked.connect(lambda: self.view_csv(db_type))
        self.view_csv_btns[db_type].clicked.connect(lambda: self.log_message("UI", f"View CSV button clicked for {db_type}", "INFO"))
        select_layout.addWidget(self.view_csv_btns[db_type])

        self.upload_csv_btns[db_type] = QPushButton("Upload CSV")
        self.upload_csv_btns[db_type].clicked.connect(lambda: self.upload_csv(db_type))
        self.upload_csv_btns[db_type].clicked.connect(lambda: self.log_message("UI", f"Upload CSV button clicked for {db_type}", "INFO"))
        select_layout.addWidget(self.upload_csv_btns[db_type])

        self.upload_multiple_csv_btns[db_type] = QPushButton("Upload CSVs")
        self.upload_multiple_csv_btns[db_type].clicked.connect(lambda: self.upload_multiple_csvs(db_type))
        self.upload_multiple_csv_btns[db_type].clicked.connect(lambda: self.log_message("UI", f"Upload CSVs button clicked for {db_type}", "INFO"))
        select_layout.addWidget(self.upload_multiple_csv_btns[db_type])

        layout.addLayout(select_layout)

        # Table view
        self.table_widgets[db_type] = QTableWidget()
        self.table_widgets[db_type].setAlternatingRowColors(True)
        self.table_widgets[db_type].setStyleSheet("""
            QTableWidget {
                alternate-background-color: #f0f0f0;
                background-color: white;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                padding: 4px;
                border: 1px solid #c0c0c0;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.table_widgets[db_type])

        # Log messages
        self.log_texts[db_type] = QTextEdit()
        self.log_texts[db_type].setReadOnly(True)
        self.log_texts[db_type].setMaximumHeight(100)
        layout.addWidget(self.log_texts[db_type])

        parent.setLayout(layout)

    def setup_migrate_tab_ui(self, parent):
        main_layout = QVBoxLayout()

        # Horizontal layout for source and target panels
        panels_layout = QHBoxLayout()

        # Source Database panel
        source_panel = QWidget()
        source_layout = QVBoxLayout(source_panel)

        source_label = QLabel("Source Database:")
        source_layout.addWidget(source_label)

        self.source_db_combo = QComboBox()
        self.source_db_combo.addItem("Select a database")
        if self.config:
            self.source_db_combo.addItems(self.config.sections())
        self.source_db_combo.currentTextChanged.connect(self.update_source_info)
        self.source_db_combo.currentTextChanged.connect(lambda text: self.log_message("UI", f"Source database changed to: {text}", "INFO"))
        source_layout.addWidget(self.source_db_combo)

        self.source_info_label = QLabel()
        source_layout.addWidget(self.source_info_label)

        self.source_table_label = QLabel("Select table/collection/label:")
        source_layout.addWidget(self.source_table_label)

        self.source_table_combo = QComboBox()
        self.source_table_combo.currentTextChanged.connect(self.update_source_schema)
        self.source_table_combo.currentTextChanged.connect(lambda text: self.log_message("UI", f"Source table/collection/label changed to: {text}", "INFO"))
        source_layout.addWidget(self.source_table_combo)

        self.source_schema_table = QTableWidget()
        source_layout.addWidget(self.source_schema_table)

        self.source_row_count_label = QLabel()
        source_layout.addWidget(self.source_row_count_label)

        self.source_columns_selected_label = QLabel("Number of columns selected: 0")
        source_layout.addWidget(self.source_columns_selected_label)

        panels_layout.addWidget(source_panel)

        # Target Database panel
        target_panel = QWidget()
        target_layout = QVBoxLayout(target_panel)

        target_label = QLabel("Target Database:")
        target_layout.addWidget(target_label)

        self.target_db_combo = QComboBox()
        self.target_db_combo.addItem("Select a database")
        if self.config:
            self.target_db_combo.addItems(self.config.sections())
        self.target_db_combo.currentTextChanged.connect(self.update_target_info)
        self.target_db_combo.currentTextChanged.connect(lambda text: self.log_message("UI", f"Target database changed to: {text}", "INFO"))
        target_layout.addWidget(self.target_db_combo)

        self.target_info_label = QLabel()
        target_layout.addWidget(self.target_info_label)

        self.target_table_label = QLabel("Target table/collection/label name:")
        target_layout.addWidget(self.target_table_label)

        self.target_table_name = QLineEdit()
        self.target_table_name.textChanged.connect(lambda text: self.log_message("UI", f"Target table/collection/label name changed to: {text}", "INFO"))
        target_layout.addWidget(self.target_table_name)

        self.target_schema_table = QTableWidget()
        target_layout.addWidget(self.target_schema_table)

        self.target_columns_changed_label = QLabel("Number of column names changed: 0")
        target_layout.addWidget(self.target_columns_changed_label)

        self.target_columns_selected_label = QLabel("Number of columns selected: 0")
        target_layout.addWidget(self.target_columns_selected_label)

        panels_layout.addWidget(target_panel)

        # Add panels layout to main layout
        main_layout.addLayout(panels_layout)

        # Add Migrate and Migrate All buttons
        button_layout = QHBoxLayout()
        self.migrate_button = QPushButton("Migrate")
        self.migrate_button.clicked.connect(self.start_migration)
        self.migrate_button.clicked.connect(lambda: self.log_message("UI", "Migrate button clicked", "INFO"))
        button_layout.addWidget(self.migrate_button)

        self.migrate_all_button = QPushButton("Migrate All")
        self.migrate_all_button.clicked.connect(self.start_migrate_all)
        self.migrate_all_button.clicked.connect(lambda: self.log_message("UI", "Migrate All button clicked", "INFO"))
        button_layout.addWidget(self.migrate_all_button)
        main_layout.addLayout(button_layout)

        # Add Progress bar
        self.progress_bar = QProgressBar()
        main_layout.addWidget(self.progress_bar)

        # Add log message box below the panels
        self.migrate_log_text = QTextEdit()
        self.migrate_log_text.setReadOnly(True)
        self.migrate_log_text.setMaximumHeight(100)
        main_layout.addWidget(self.migrate_log_text)

        parent.setLayout(main_layout)

    def update_migration_ui(self, source_db, target_db, source_item, target_item):
        # Update source combobox and schema
        self.source_db_combo.setCurrentText(source_db)
        self.source_table_combo.setCurrentText(source_item)
        self.update_source_schema(source_item)

        # Update target name and schema
        self.target_db_combo.setCurrentText(target_db)
        self.target_table_name.setText(target_item)
        self.update_target_schema(source_db, target_db, source_item)

        # Update row and column counts
        source_schema = self.get_schema(source_db, source_item)
        row_count = self.get_row_count(source_db, source_item)
        self.source_row_count_label.setText(f"Number of rows: {row_count}")
        self.source_columns_selected_label.setText(f"Number of columns selected: {len(source_schema)}")
        self.target_columns_selected_label.setText(f"Number of columns selected: {len(source_schema)}")

        # Update the application to process events and refresh the UI
        QApplication.processEvents()
        
    def update_selected_columns_count(self):
        selected_count = 0
        for i in range(self.source_schema_table.rowCount()):
            checkbox = self.source_schema_table.cellWidget(i, 0)
            if checkbox and checkbox.isChecked():
                selected_count += 1
        
        self.source_columns_selected_label.setText(f"Number of columns selected: {selected_count}")
        self.target_columns_selected_label.setText(f"Number of columns selected: {selected_count}")       

    def show_warning(self, title, message):
        QMessageBox.warning(self, title, message)
        self.log_message("UI", f"Warning shown: {title} - {message}", "WARN")

    # def update_target_info(self, db_name):
    #     if db_name == "Select a database":
    #         self.target_info_label.setText("")
    #         self.target_table_name.clear()
    #         self.target_schema_table.clearContents()
    #         return

    #     db_info = self.get_db_info(db_name)
    #     self.target_info_label.setText(db_info)

    #     # Update the target schema with the new database type
    #     source_db = self.source_db_combo.currentText()
    #     source_table = self.source_table_combo.currentText()
    #     if source_db and source_table:
    #         self.update_target_schema(source_db, db_name, source_table)


    def update_target_info(self, db_name):
        if db_name == "Select a database":
            self.target_info_label.setText("")
            self.target_table_name.clear()
            self.clear_target_schema()
            return

        db_info = self.get_db_info(db_name)
        self.target_info_label.setText(db_info)

        # Update the target schema with the new database type
        source_db = self.source_db_combo.currentText()
        source_table = self.source_table_combo.currentText()
        if source_db and source_table:
            self.update_target_schema(source_db, db_name, source_table)
        else:
            self.clear_target_schema()
            
    def update_target_schema(self, source_db, target_db, table_name):
        source_schema = self.get_schema(source_db, table_name)
        target_schema = self.convert_schema(source_db, target_db, source_schema)
        self.populate_schema_table(self.target_schema_table, target_schema, editable=True, is_target=True)
        self.update_selected_columns_count()
        self.update_changed_columns_count()  # Call this to initialize the count

    def convert_schema(self, source_db, target_db, schema):
        if source_db == target_db:
            return schema

        converted_schema = []
        for column, data_type in schema:
            if target_db == "PostgreSQL":
                converted_type = self.to_postgresql_type(data_type)
            elif target_db == "MongoDB":
                converted_type = self.to_mongodb_type(data_type)
            else:  # Neo4j
                converted_type = self.to_neo4j_type(data_type)
            converted_schema.append((column, converted_type))
        return converted_schema

    def to_postgresql_type(self, data_type):
        # Add more type conversions as needed
        type_mapping = {
            'int': 'INTEGER',
            'float': 'FLOAT',
            'str': 'TEXT',
            'bool': 'BOOLEAN',
            'datetime': 'TIMESTAMP',
        }
        return type_mapping.get(data_type.lower(), 'TEXT')

    def to_mongodb_type(self, data_type):
        # MongoDB doesn't enforce schema, so we'll use general types
        type_mapping = {
            'int': 'Number',
            'float': 'Number',
            'str': 'String',
            'bool': 'Boolean',
            'datetime': 'Date',
        }
        return type_mapping.get(data_type.lower(), 'Mixed')

    def to_neo4j_type(self, data_type):
        # Neo4j doesn't have strict types, but we'll use general categories
        type_mapping = {
            'int': 'Integer',
            'float': 'Float',
            'str': 'String',
            'bool': 'Boolean',
            'datetime': 'DateTime',
        }
        return type_mapping.get(data_type.lower(), 'String')

    def start_migration(self):
        source_db = self.source_db_combo.currentText()
        target_db = self.target_db_combo.currentText()
        source_table = self.source_table_combo.currentText()
        target_table = self.target_table_name.text()
        
        if source_db == "Select a database" or target_db == "Select a database" or not source_table or not target_table:
            self.log_message("Migration", "Please select source and target databases and specify table names.", "WARN")
            return

        selected_columns = []
        target_columns = []
        for i in range(self.source_schema_table.rowCount()):
            checkbox = self.source_schema_table.cellWidget(i, 0)
            if checkbox and checkbox.isChecked():
                source_column = self.source_schema_table.item(i, 1).text()
                target_column = self.target_schema_table.item(i, 0).text()
                selected_columns.append(source_column)
                target_columns.append(target_column)

        if not selected_columns:
            self.log_message("Migration", "Please select at least one column to migrate.", "WARN")
            return

        self.log_message("Migration", f"Migration started from source [{source_db}] to target [{target_db}]", "INFO")
        self.log_message("Migration", f"Source table/collection/label: {source_table}", "INFO")
        self.log_message("Migration", f"Target table/collection/label: {target_table}", "INFO")
        self.log_message("Migration", f"Columns: {', '.join(selected_columns)}", "INFO")

        self.worker = MigrationWorker(self, source_db, target_db, source_table, target_table, selected_columns, target_columns)
        self.worker.progress.connect(self.update_progress)
        self.worker.log.connect(self.log_message)
        self.worker.finished.connect(self.migration_finished)
        self.worker.start()

        self.migrate_button.setEnabled(False)

    def start_migrate_all(self):
        source_db = self.source_db_combo.currentText()
        target_db = self.target_db_combo.currentText()

        if source_db == "Select a database" or target_db == "Select a database":
            self.log_message("Migration", "Please select source and target databases.", "WARN")
            return

        if source_db == target_db:
            reply = QMessageBox.warning(self, "Warning",
                                        "Source and target databases are the same. Do you want to continue?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return

        # Get all tables/collections/labels from the source database
        if source_db.lower() == "postgresql":
            items = self.get_postgresql_tables()
        elif source_db.lower() == "mongodb":
            items = self.get_mongodb_collections()
        elif source_db.lower() == "neo4j":
            items = self.get_neo4j_labels()
        else:
            self.log_message("Migration", f"Unsupported source database type: {source_db}", "ERROR")
            return

        # Prepare report data
        report_data = {
            'total_items': len(items),
            'total_time': 0,
            'items': []
        }

        # Start migration for each item
        total_items = len(items)
        start_time = time.time()
        for i, item in enumerate(items):
            self.log_message("Migration", f"Starting migration for {item} ({i+1}/{total_items})", "INFO")
            
            # Update UI for current migration
            self.update_migration_ui(source_db, target_db, item, item)
            
            # Perform the migration
            item_start_time = time.time()
            result, migrated, failed, error = self.migrate_item(source_db, target_db, item, item)
            item_time = time.time() - item_start_time

            # Collect report data
            report_data['items'].append({
                'name': item,
                'records': self.get_row_count(source_db, item),
                'result': result,
                'migrated': migrated,
                'failed': failed,
                'time': item_time,
                'error': error
            })

            # Update progress
            progress = int((i + 1) / total_items * 100)
            self.progress_bar.setValue(progress)

        report_data['total_time'] = time.time() - start_time
        self.log_message("Migration", "All migrations completed.", "INFO")

        # Show migration report
        report_dialog = MigrationReport(report_data)
        report_dialog.exec()

    def migrate_item(self, source_db, target_db, source_item, target_item):
        try:
            # Get schema for the source item
            source_schema = self.get_schema(source_db, source_item)
            source_columns = [col for col, _ in source_schema]
            
            # Get the target schema (which may have different column names)
            target_schema = self.convert_schema(source_db, target_db, source_schema)
            target_columns = [col for col, _ in target_schema]

            # Create MigrationWorker
            worker = MigrationWorker(self, source_db, target_db, source_item, target_item, source_columns, target_columns)
            worker.progress.connect(self.update_progress)
            worker.log.connect(self.log_message)

            # Start migration
            worker.run()  # Run synchronously to ensure sequential migration

            # Get migration results
            total_rows = worker.total_rows
            migrated_rows = worker.migrated_rows
            failed_rows = total_rows - migrated_rows

            if failed_rows == 0:
                result = "OK"
            elif migrated_rows == 0:
                result = "Fail"
            else:
                result = f"Partially migrated ({migrated_rows}/{total_rows})"

            return result, migrated_rows, failed_rows, worker.error_message

        except Exception as e:
            error_message = str(e)
            self.log_message("Migration", f"Error migrating {source_item}: {error_message}", "ERROR")
            return "Fail", 0, self.get_row_count(source_db, source_item), error_message

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def migration_finished(self):
        self.log_message("Migration", "Migration completed.", "INFO")
        self.migrate_button.setEnabled(True)

    def get_db_info(self, db_name):
        if db_name not in self.config:
            return f"No configuration found for {db_name}"

        config = self.config[db_name]
        if db_name == "PostgreSQL":
            return (f"Host: {config.get('host', 'N/A')}\n"
                    f"Port: {config.get('port', 'N/A')}\n"
                    f"Database: {config.get('database', 'N/A')}\n"
                    f"User: {config.get('user', 'N/A')}")
        elif db_name == "MongoDB":
            return (f"Host: {config.get('host', 'N/A')}\n"
                    f"Database: {config.get('database', 'N/A')}\n"
                    f"User: {config.get('user', 'N/A')}")
        else:  # Neo4j
            # Check for both 'url' and 'host' to accommodate different config styles
            connection = config.get('url', config.get('host', 'N/A'))
            return (f"Connection: {connection}\n"
                    f"User: {config.get('user', 'N/A')}")

    def get_schema(self, db_name, table_name):
        if db_name.lower() == "postgresql":
            return self.get_postgresql_schema(table_name)
        elif db_name.lower() == "mongodb":
            return self.get_mongodb_schema(table_name)
        else:  # Neo4j
            return self.get_neo4j_schema(table_name)

    def get_postgresql_schema(self, table_name):
        self.pg_cur.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
        """)
        return self.pg_cur.fetchall()

    def get_mongodb_schema(self, collection_name):
        collection = self.mongo_db[collection_name]
        sample_doc = collection.find_one()
        return [(key, type(value).__name__) for key, value in sample_doc.items()]

    def get_neo4j_schema(self, label):
        with self.neo4j_driver.session() as session:
            result = session.run(f"MATCH (n:`{label}`) RETURN n LIMIT 1")
            sample_node = result.single()['n']
            return [(key, type(value).__name__) for key, value in sample_node.items()]

    def get_row_count(self, db_name, table_name):
        if db_name.lower() == "postgresql":
            self.pg_cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            return self.pg_cur.fetchone()[0]
        elif db_name.lower() == "mongodb":
            return self.mongo_db[table_name].count_documents({})
        else:  # Neo4j
            with self.neo4j_driver.session() as session:
                result = session.run(f"MATCH (n:`{table_name}`) RETURN COUNT(n) AS count")
                return result.single()['count']

    def update_source_schema(self, table_name):
        if not table_name:
            return

        source_db = self.source_db_combo.currentText()
        schema = self.get_schema(source_db, table_name)
        row_count = self.get_row_count(source_db, table_name)

        self.populate_schema_table(self.source_schema_table, schema, with_checkbox=True)
        self.source_row_count_label.setText(f"Number of rows: {row_count}")
        self.update_selected_columns_count()

        # Update target table name and schema
        self.target_table_name.setText(table_name)
        target_db = self.target_db_combo.currentText()
        self.update_target_schema(source_db, target_db, table_name)

    def populate_schema_table(self, table_widget, schema, editable=False, with_checkbox=False, is_target=False):
        table_widget.blockSignals(True)  # Block signals temporarily
        
        # Clear the existing contents of the table
        table_widget.clearContents()
        table_widget.setRowCount(0)
        
        if with_checkbox:
            table_widget.setColumnCount(3)
            table_widget.setHorizontalHeaderLabels(["Select", "Column Name", "Data Type"])
        else:
            table_widget.setColumnCount(2)
            table_widget.setHorizontalHeaderLabels(["Column Name", "Data Type"])
        
        table_widget.setRowCount(len(schema))
        
        for i, (column, data_type) in enumerate(schema):
            if with_checkbox:
                checkbox = QCheckBox()
                checkbox.setChecked(True)
                checkbox.stateChanged.connect(self.update_selected_columns_count)
                table_widget.setCellWidget(i, 0, checkbox)
                
                name_item = QTableWidgetItem(column)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table_widget.setItem(i, 1, name_item)
                
                type_item = QTableWidgetItem(data_type)
                type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table_widget.setItem(i, 2, type_item)
            else:
                name_item = QTableWidgetItem(column)
                type_item = QTableWidgetItem(data_type)
                
                if editable and is_target:
                    name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)
                    name_item.setData(Qt.ItemDataRole.UserRole, column)  # Store original name
                else:
                    name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                table_widget.setItem(i, 0, name_item)
                table_widget.setItem(i, 1, type_item)

        table_widget.resizeColumnsToContents()
        
        table_widget.blockSignals(False)  # Unblock signals
        
        if with_checkbox:
            self.update_selected_columns_count()
        
        if is_target:
            table_widget.itemChanged.connect(self.update_changed_columns_count)

    def update_changed_columns_count(self, item=None):
        if item and item.column() != 0:  # Only process changes in the first column (column names)
            return

        changed_count = 0
        for i in range(self.target_schema_table.rowCount()):
            item = self.target_schema_table.item(i, 0)
            original_name = item.data(Qt.ItemDataRole.UserRole)
            current_name = item.text()
            if original_name != current_name:
                changed_count += 1
        
        self.target_columns_changed_label.setText(f"Number of column names changed: {changed_count}")

    def update_combo_box(self, db_type, item_name):
        combo_box = self.select_combos[db_type]
        if combo_box.findText(item_name) == -1:
            combo_box.addItem(item_name)
        combo_box.setCurrentText(item_name)

    def load_tables(self, db_type):
        if self.pg_cur:
            try:
                self.pg_cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name ASC")
                tables = [table[0] for table in self.pg_cur.fetchall()]
                self.select_combos[db_type].clear()
                self.select_combos[db_type].addItems(tables)
                self.log_message(db_type, f"Loaded tables: {', '.join(tables)}", "INFO")
            except Exception as e:
                self.log_message(db_type, f"Error loading tables: {str(e)}", "ERROR")
                    
    def load_labels(self, db_type):
        with self.neo4j_driver.session() as session:
            result = session.run("CALL db.labels()")
            labels = sorted([record["label"] for record in result])
            self.select_combos[db_type].clear()
            self.select_combos[db_type].addItems(labels)
            self.log_message(db_type, f"Loaded labels: {', '.join(labels)}", "INFO")

    def load_collections(self, db_type):
        collections = sorted(self.mongo_db.list_collection_names())
        self.select_combos[db_type].clear()
        self.select_combos[db_type].addItems(collections)
        self.log_message(db_type, f"Loaded collections: {', '.join(collections)}", "INFO")
        
    def load_data(self, db_type):
        selected_item = self.select_combos[db_type].currentText()
        if not selected_item:
            return

        self.log_message(db_type, f"Loading data for {selected_item}", "INFO")

        if db_type == "PostgreSQL":
            self.load_postgresql_data(selected_item)
        elif db_type == "MongoDB":
            self.load_mongodb_data(selected_item)
        else:  # Neo4j
            self.load_neo4j_data(selected_item)

    def load_postgresql_data(self, table_name):
        try:
            self.pg_cur.execute(f'SELECT * FROM "{table_name}"')
            rows = self.pg_cur.fetchall()
            columns = [desc[0] for desc in self.pg_cur.description]
            self.populate_table_widget("PostgreSQL", columns, rows)
        except Exception as e:
            self.log_message("PostgreSQL", f"Error loading data: {str(e)}", "ERROR")

    def load_mongodb_data(self, collection_name):
        try:
            collection = self.mongo_db[collection_name]
            documents = list(collection.find())
            if documents:
                columns = list(documents[0].keys())
                rows = [[str(doc.get(col, '')) for col in columns] for doc in documents]
                self.populate_table_widget("MongoDB", columns, rows)
            else:
                self.log_message("MongoDB", "No documents found in the collection", "WARN")
        except Exception as e:
            self.log_message("MongoDB", f"Error loading data: {str(e)}", "ERROR")

    def load_neo4j_data(self, label):
        with self.neo4j_driver.session() as session:
            result = session.run(f"MATCH (n:`{label}`) RETURN n")
            records = list(result)
            if records:
                columns = list(records[0]['n'].keys())
                rows = [[str(record['n'].get(col, '')) for col in columns] for record in records]
                self.populate_table_widget("Neo4j", columns, rows)
            else:
                self.log_message("Neo4j", f"No nodes found with label: {label}", "WARN")

    def populate_table_widget(self, db_type, columns, rows):
        table_widget = self.table_widgets[db_type]
        table_widget.setRowCount(len(rows))
        table_widget.setColumnCount(len(columns))
        table_widget.setHorizontalHeaderLabels(columns)

        # Set font that supports Korean characters
        font = QFont("Malgun Gothic", 10)  # You can change this to another font that supports Korean
        table_widget.setFont(font)

        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                table_widget.setItem(i, j, QTableWidgetItem(str(value)))

        table_widget.resizeColumnsToContents()
        self.log_message(db_type, f"Loaded {len(rows)} rows", "INFO")

    def download_csv(self, db_type):
        selected_item = self.select_combos[db_type].currentText()
        if not selected_item:
            self.log_message(db_type, "No item selected", "WARN")
            return

        file_name, _ = QFileDialog.getSaveFileName(self, "Save CSV", f"{selected_item}.csv", "CSV Files (*.csv)")
        if not file_name:
            return

        try:
            if db_type == "PostgreSQL":
                self.download_postgresql_csv(selected_item, file_name)
            elif db_type == "MongoDB":
                self.download_mongodb_csv(selected_item, file_name)
            else:  # Neo4j
                self.download_neo4j_csv(selected_item, file_name)
            
            self.log_message(db_type, f"CSV file saved: {file_name}", "INFO")
        except Exception as e:
            self.log_message(db_type, f"Error saving CSV: {str(e)}", "ERROR")

    def download_postgresql_csv(self, table_name, file_name):
        self.pg_cur.execute(f'SELECT * FROM "{table_name}"')
        rows = self.pg_cur.fetchall()
        columns = [desc[0] for desc in self.pg_cur.description]
        
        df = pd.DataFrame(rows, columns=columns)
        df.to_csv(file_name, index=False, encoding='utf-8-sig')

    def download_mongodb_csv(self, collection_name, file_name):
        collection = self.mongo_db[collection_name]
        documents = list(collection.find())
        
        if not documents:
            raise ValueError("No documents found in the collection")
        
        df = pd.DataFrame(documents)
        df.to_csv(file_name, index=False, encoding='utf-8-sig')

    def download_neo4j_csv(self, label, file_name):
        with self.neo4j_driver.session() as session:
            result = session.run(f"MATCH (n:`{label}`) RETURN n")
            records = [dict(record['n']) for record in result]
            
            if not records:
                raise ValueError(f"No nodes found with label: {label}")
            
            df = pd.DataFrame(records)
            df.to_csv(file_name, index=False, encoding='utf-8-sig')

    def download_all(self, db_type):
        if db_type == "PostgreSQL":
            items = self.get_postgresql_tables()
        elif db_type == "MongoDB":
            items = self.get_mongodb_collections()
        else:  # Neo4j
            items = self.get_neo4j_labels()

        if not items:
            self.log_message(db_type, f"No {db_type} items found to download", "WARN")
            return

        directory = QFileDialog.getExistingDirectory(self, "Select Directory to Save CSVs")
        if not directory:
            return

        progress = QProgressDialog("Downloading CSVs...", "Cancel", 0, len(items), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        for i, item in enumerate(items):
            if progress.wasCanceled():
                break

            file_name = os.path.join(directory, f"{item}.csv")
            try:
                if db_type == "PostgreSQL":
                    self.download_postgresql_csv(item, file_name)
                elif db_type == "MongoDB":
                    self.download_mongodb_csv(item, file_name)
                else:  # Neo4j
                    self.download_neo4j_csv(item, file_name)
                
                self.log_message(db_type, f"CSV file saved: {file_name}", "INFO")
            except Exception as e:
                self.log_message(db_type, f"Error saving CSV for {item}: {str(e)}", "ERROR")

            progress.setValue(i + 1)

        self.log_message(db_type, "Finished downloading all CSVs", "INFO")

    def upload_multiple_csvs(self, db_type):
        file_names, _ = QFileDialog.getOpenFileNames(self, "Select CSV Files", "", "CSV Files (*.csv)")
        if not file_names:
            return

        progress = QProgressDialog("Uploading CSVs...", "Cancel", 0, len(file_names), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        for i, file_name in enumerate(file_names):
            if progress.wasCanceled():
                break

            try:
                df = pd.read_csv(file_name, encoding='utf-8-sig')
                item_name = os.path.splitext(os.path.basename(file_name))[0]

                if db_type == "PostgreSQL":
                    self.upload_postgresql_csv(item_name, df)
                elif db_type == "MongoDB":
                    self.upload_mongodb_csv(item_name, df)
                else:  # Neo4j
                    self.upload_neo4j_csv(item_name, df)
                self.log_message(db_type, f"CSV file uploaded: {file_name}", "INFO")
                self.update_combo_box(db_type, item_name)
            except Exception as e:
                self.log_message(db_type, f"Error uploading CSV {file_name}: {str(e)}", "ERROR")

            progress.setValue(i + 1)

        if db_type == "PostgreSQL":
            self.load_tables(db_type)
        elif db_type == "MongoDB":
            self.load_collections(db_type)
        else:  # Neo4j
            self.load_labels(db_type)

        self.log_message(db_type, "Finished uploading multiple CSVs", "INFO")

    def get_postgresql_tables(self):
        if self.pg_cur:
            self.pg_cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            return [table[0] for table in self.pg_cur.fetchall()]
        return []

    def get_mongodb_collections(self):
        return self.mongo_db.list_collection_names()

    def get_neo4j_labels(self):
        with self.neo4j_driver.session() as session:
            result = session.run("CALL db.labels()")
            return [record["label"] for record in result]

    def view_csv(self, db_type):
        selected_item = self.select_combos[db_type].currentText()
        if not selected_item:
            self.log_message(db_type, "No item selected", "WARN")
            return

        file_name = f"{selected_item}.csv"
        file_path = os.path.join(os.getcwd(), file_name)

        if not os.path.exists(file_path):
            self.download_csv(db_type)

        if os.path.exists(file_path):
            dialog = CsvViewerDialog(file_path)
            dialog.exec()
        else:
            self.log_message(db_type, f"CSV file not found: {file_name}", "WARN")

    def upload_csv(self, db_type):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv)")
        if not file_name:
            return

        try:
            # Try different encodings
            encodings = ['utf-8-sig', 'cp949', 'euc-kr']
            df = None
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_name, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue

            if df is None:
                raise ValueError("Unable to decode the CSV file with supported encodings.")

            item_name = os.path.splitext(os.path.basename(file_name))[0]

            if db_type == "PostgreSQL":
                self.upload_postgresql_csv(item_name, df)
                self.load_tables(db_type)
            elif db_type == "MongoDB":
                self.upload_mongodb_csv(item_name, df)
                self.load_collections(db_type)
            else:  # Neo4j
                self.upload_neo4j_csv(item_name, df)
                self.load_labels(db_type)

            self.log_message(db_type, f"CSV file uploaded: {file_name}", "INFO")
            self.load_data(db_type)
            
            # Update the combo box
            self.update_combo_box(db_type, item_name)
            
        except Exception as e:
            self.log_message(db_type, f"Error uploading CSV: {str(e)}", "ERROR")

    def upload_postgresql_csv(self, table_name, df):
        # Create table
        columns = []
        for column, dtype in df.dtypes.items():
            if dtype == 'int64':
                col_type = 'INTEGER'
            elif dtype == 'float64':
                col_type = 'FLOAT'
            else:
                col_type = 'TEXT'
            columns.append(f'"{column}" {col_type}')
        
        create_table_query = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(columns)})'
        self.pg_cur.execute(create_table_query)
        
        # Insert data
        columns = ', '.join(f'"{col}"' for col in df.columns)
        values = ', '.join(['%s'] * len(df.columns))
        insert_query = f'INSERT INTO "{table_name}" ({columns}) VALUES ({values})'
        
        data = [tuple(row) for row in df.values]
        self.pg_cur.executemany(insert_query, data)
        self.pg_conn.commit()

    def upload_mongodb_csv(self, collection_name, df):
        collection = self.mongo_db[collection_name]
        records = df.to_dict('records')
        collection.insert_many(records)

    def upload_neo4j_csv(self, label, df):
        with self.neo4j_driver.session() as session:
            # Clear existing nodes with this label
            session.run(f"MATCH (n:`{label}`) DETACH DELETE n")
            
            # Create new nodes
            for _, row in df.iterrows():
                properties = ', '.join([f"`{col}`: ${col}" for col in df.columns])
                cypher_query = f"CREATE (:`{label}` {{{properties}}})"
                session.run(cypher_query, **row.to_dict())



    def update_source_info(self, db_name):
        if db_name == "Select a database":
            self.clear_source_info()
            return

        db_info = self.get_db_info(db_name)
        self.source_info_label.setText(db_info)

        try:
            if db_name.lower() == "postgresql":
                items = sorted(self.get_postgresql_tables())
            elif db_name.lower() == "mongodb":
                items = sorted(self.get_mongodb_collections())
            else:  # Neo4j
                if self.neo4j_driver is None:
                    raise Exception("Neo4j is not connected. Please check the connection and try again.")
                items = sorted(self.get_neo4j_labels())

            self.source_table_combo.clear()
            if items:
                self.source_table_combo.addItems(items)
                self.source_table_combo.setCurrentIndex(0)  # Select the first item
                self.update_source_schema(items[0])
            else:
                self.clear_source_schema()
                self.log_message(db_name, "No tables/collections/labels found in the selected database", "WARN")

            # Set the target database to the same type
            self.target_db_combo.setCurrentText(db_name)
        except Exception as e:
            error_message = f"Error loading items for {db_name}: {str(e)}"
            self.log_message(db_name, error_message, "ERROR")
            self.clear_source_info()

    def clear_source_info(self):
        self.source_info_label.setText("")
        self.source_table_combo.clear()
        self.clear_source_schema()

    def clear_source_schema(self):
        self.source_schema_table.clearContents()
        self.source_schema_table.setRowCount(0)
        self.source_row_count_label.setText("")
        self.source_columns_selected_label.setText("Number of columns selected: 0")
        self.target_table_name.clear()
        self.clear_target_schema()

    def clear_target_schema(self):
        self.target_schema_table.clearContents()
        self.target_schema_table.setRowCount(0)
        self.target_columns_changed_label.setText("Number of column names changed: 0")
        self.target_columns_selected_label.setText("Number of columns selected: 0")
        
    def closeEvent(self, event):
        self.disconnect_databases()
        event.accept()

    def get_postgresql_data(self, table_name, columns):
        columns_str = ", ".join(f'"{col}"' for col in columns)
        query = f'SELECT {columns_str} FROM "{table_name}"'
        self.log_message("PostgreSQL", f"Executing query: {query}", "DEBUG")
        self.pg_cur.execute(query)
        return self.pg_cur.fetchall()

    def get_mongodb_data(self, collection_name, columns):
        collection = self.mongo_db[collection_name]
        projection = {col: 1 for col in columns}
        projection['_id'] = 0  # Exclude the _id field
        query = f"db.{collection_name}.find({{}}, {projection})"
        self.log_message("MongoDB", f"Executing query: {query}", "DEBUG")
        return list(collection.find({}, projection))

    def get_neo4j_data(self, label, columns):
        query = f"MATCH (n:`{label}`) RETURN {', '.join(f'n.{col} AS {col}' for col in columns)}"
        self.log_message("Neo4j", f"Executing query: {query}", "DEBUG")
        with self.neo4j_driver.session() as session:
            result = session.run(query)
            return [dict(record) for record in result]


    def create_postgresql_table(self, table_name, columns):
        columns_def = []
        for col in columns:
            if isinstance(col, tuple) and len(col) == 2:
                col_name, data_type = col
            elif isinstance(col, str):
                col_name = col
                data_type = 'TEXT'  # Default to TEXT if type is not specified
            else:
                raise ValueError(f"Unexpected column format: {col}")

            if data_type == 'DateTime':
                col_type = 'TIMESTAMP WITH TIME ZONE'
            elif data_type == 'float':
                col_type = 'DOUBLE PRECISION'
            elif data_type == 'int':
                col_type = 'INTEGER'
            else:
                col_type = 'TEXT'
            
            columns_def.append(f'"{col_name}" {col_type}')
        
        query = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(columns_def)})'
        self.log_message("PostgreSQL", f"Creating table: {query}", "DEBUG")
        self.pg_cur.execute(query)
        self.pg_conn.commit()

    def create_mongodb_collection(self, collection_name):
        self.log_message("MongoDB", f"Creating collection: {collection_name}", "DEBUG")
        self.mongo_db.create_collection(collection_name)

    def create_neo4j_label(self, label):
        # Neo4j doesn't require explicit label creation
        self.log_message("Neo4j", f"Label '{label}' will be created automatically during data insertion", "DEBUG")

    def get_data(self, db_name, table_name, columns):
        db_name = db_name.lower()
        if db_name == "postgresql":
            return self.get_postgresql_data(table_name, columns)
        elif db_name == "mongodb":
            return self.get_mongodb_data(table_name, columns)
        elif db_name == "neo4j":
            return self.get_neo4j_data(table_name, columns)
        else:
            raise ValueError(f"Unsupported database type: {db_name}")
        
    def create_target_table(self, db_name, table_name, columns):
        db_name = db_name.lower()
        if db_name == "postgresql":
            self.create_postgresql_table(table_name, columns)
        elif db_name == "mongodb":
            self.create_mongodb_collection(table_name)
        elif db_name == "neo4j":
            self.create_neo4j_label(table_name)
        else:
            raise ValueError(f"Unsupported database type: {db_name}")

    def insert_row(self, db_name, table_name, columns, row):
        db_name = db_name.lower()
        if db_name == "postgresql":
            self.insert_postgresql_row(table_name, columns, row)
        elif db_name == "mongodb":
            self.insert_mongodb_row(table_name, columns, row)
        elif db_name == "neo4j":
            self.insert_neo4j_row(table_name, columns, row)
        else:
            raise ValueError(f"Unsupported database type: {db_name}")


    @staticmethod
    def convert_for_postgresql(obj):
        if isinstance(obj, DateTime):
            # Convert Neo4j DateTime to Python datetime
            py_datetime = obj.to_native()
            # Make it timezone-aware if it's not
            if py_datetime.tzinfo is None:
                py_datetime = py_datetime.replace(tzinfo=pytz.UTC)
            return py_datetime
        elif isinstance(obj, Date):
            # Convert Neo4j Date to Python date
            return date(obj.year, obj.month, obj.day)
        elif isinstance(obj, date):
            return obj
        elif isinstance(obj, Decimal):
            return float(obj)
        return obj

    def insert_postgresql_row(self, table_name, columns, row):
        columns_str = ", ".join(f'"{col}"' for col in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        query = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders})'
        if self.pg_cur.rowcount == 0:  # Log only the first insert
            self.log_message("PostgreSQL", f"Inserting data: {query}", "DEBUG")
        
        # Convert row to a list if it's a dictionary
        if isinstance(row, dict):
            row = [self.convert_for_postgresql(row.get(col, None)) for col in columns]
        else:
            row = [self.convert_for_postgresql(val) for val in row]
        
        self.pg_cur.execute(query, row)
        self.pg_conn.commit()
        


    @staticmethod
    def convert_for_mongodb(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, date):
            return datetime.combine(obj, datetime.min.time())
        return obj

    def insert_mongodb_row(self, collection_name, columns, row):
        if isinstance(row, dict):
            document = {k: self.convert_for_mongodb(v) for k, v in row.items()}
        else:
            document = {col: self.convert_for_mongodb(val) for col, val in zip(columns, row)}
        
        query = f"db.{collection_name}.insertOne({document})"
        if self.mongo_db[collection_name].count_documents({}) == 0:  # Log only the first insert
            self.log_message("MongoDB", f"Inserting data: {query}", "DEBUG")
        self.mongo_db[collection_name].insert_one(document)
        

    def decimal_to_float(value):
        if isinstance(value, Decimal):
            return float(value)
        return value

    def decimal_to_string(value):
        if isinstance(value, Decimal):
            return str(value)
        return value

    @staticmethod
    def custom_decimal_conversion(value):
        if isinstance(value, Decimal):
            if value.as_tuple().exponent >= 0:  # It's an integer
                return int(value)
            else:
                return float(value)
        return value

    def insert_neo4j_row(self, label, columns, row):
        if isinstance(row, dict):
            properties = ", ".join(f"`{col}`: ${col}" for col in row.keys())
            params = {k: self.custom_decimal_conversion(v) for k, v in row.items()}
        else:
            properties = ", ".join(f"`{col}`: ${col}" for col in columns)
            params = {col: self.custom_decimal_conversion(val) for col, val in zip(columns, row)}
        
        query = f"CREATE (:`{label}` {{{properties}}})"
        with self.neo4j_driver.session() as session:
            session.run(query, params)


    def get_relationship_types(self):
        try:
            with self.neo4j_driver.session() as session:
                result = session.run("CALL db.relationshipTypes()")
                return sorted([record["relationshipType"] for record in result])
        except Exception as e:
            self.log_message("Neo4j", f"Error fetching relationship types: {str(e)}", "ERROR")
            return []

    def setup_relate_tab_ui(self, parent):
        layout = QVBoxLayout()

        # Source and Target Label selection
        labels_layout = QHBoxLayout()
        
        source_layout = QVBoxLayout()
        source_layout.addWidget(QLabel("Source Label:"))
        self.source_label_combo = QComboBox()
        source_layout.addWidget(self.source_label_combo)
        
        target_layout = QVBoxLayout()
        target_layout.addWidget(QLabel("Target Label:"))
        self.target_label_combo = QComboBox()
        target_layout.addWidget(self.target_label_combo)
        
        labels_layout.addLayout(source_layout)
        labels_layout.addLayout(target_layout)
        layout.addLayout(labels_layout)

        # Properties selection and tables
        props_layout = QHBoxLayout()
        
        # Source properties
        source_props_layout = QVBoxLayout()
        self.source_props_list = QListWidget()
        source_props_layout.addWidget(QLabel("Source Properties:"))
        source_props_layout.addWidget(self.source_props_list)
        self.source_props_table = QTableWidget()
        source_props_layout.addWidget(self.source_props_table)
        props_layout.addLayout(source_props_layout)
        
        # Target properties
        target_props_layout = QVBoxLayout()
        self.target_props_list = QListWidget()
        target_props_layout.addWidget(QLabel("Target Properties:"))
        target_props_layout.addWidget(self.target_props_list)
        self.target_props_table = QTableWidget()
        target_props_layout.addWidget(self.target_props_table)
        props_layout.addLayout(target_props_layout)
        
        layout.addLayout(props_layout)

        # Cypher Query Text Edit
        self.cypher_query_edit = QTextEdit()
        self.cypher_query_edit.setFixedHeight(100)  # Set a fixed height
        self.cypher_highlighter = CypherHighlighter(self.cypher_query_edit.document())
        layout.addWidget(QLabel("Cypher Query:"))
        layout.addWidget(self.cypher_query_edit)

        # Create and View Relationship buttons
        button_layout = QHBoxLayout()

        # Relationship Name
        rel_layout = QHBoxLayout()
        # With these lines:
        self.relationship_name_combo = QComboBox()
        self.relationship_name_combo.setEditable(True)
        self.relationship_name_combo.addItems(self.get_relationship_types())
        self.relationship_name_combo.setCurrentText("Relates")  # Default value

        # Set blue color for relationship name
        palette = self.relationship_name_combo.palette()
        palette.setColor(QPalette.ColorRole.Text, QColor("blue"))
        self.relationship_name_combo.setPalette(palette)

        rel_layout.addWidget(QLabel("Relationship Name:"))
        rel_layout.addWidget(self.relationship_name_combo)

        button_layout.addLayout(rel_layout)

        # Create Relationships button
        self.create_rel_button = QPushButton("Create Relationships")
        self.create_rel_button.clicked.connect(self.create_relationships)
        button_layout.addWidget(self.create_rel_button)

        # View Relationships button
        self.view_rel_button = QPushButton("View Relationships")
        self.view_rel_button.clicked.connect(self.view_relationships)
        button_layout.addWidget(self.view_rel_button)

        # View Graphically button
        self.view_graph_button = QPushButton("View Graphically")
        self.view_graph_button.clicked.connect(self.view_relationships_graphically)
        button_layout.addWidget(self.view_graph_button)


        layout.addLayout(button_layout)

        # Progress bar
        self.relate_progress_bar = QProgressBar()
        layout.addWidget(self.relate_progress_bar)

        # Log area
        self.relate_log_text = QTextEdit()
        self.relate_log_text.setReadOnly(True)
        self.relate_log_text.setMaximumHeight(100)  # Set a maximum height
        layout.addWidget(QLabel("Log Messages:"))
        layout.addWidget(self.relate_log_text)
        parent.setLayout(layout)

        # Move signal connections here
        self.connect_relate_tab_signals()

        # Initial population of label combos
        self.populate_label_combos()

        # Initial update of Cypher query
        self.update_cypher_query()
        
    



    def view_relationships_graphically(self):
        relationship_name = self.relationship_name_combo.currentText()
        if not relationship_name:
            self.log_message("Relate", "Please select a relationship name", "ERROR")
            return

        node_limit = 20  # Initial node limit

        # Base query template
        base_query = """MATCH (source)-[r:`{}`]->(target)
        RETURN id(source) as source_id,
            id(target) as target_id,
            labels(source) as source_labels,
            labels(target) as target_labels,
            properties(source) as source_props,
            properties(target) as target_props,
            type(r) as relationship_type
        LIMIT {}"""

        def update_graph(limit):
            nonlocal node_limit
            node_limit = limit
            
            current_query = base_query.format(relationship_name, limit)
            query_display.setPlainText(current_query)
            
            try:
                with self.neo4j_driver.session() as session:
                    result = session.run(current_query)
                    records = list(result)
                    
                    if not records:
                        self.log_message("Relate", f"No relationships found for type: {relationship_name}", "INFO")
                        return

                    G = nx.DiGraph()
                    source_nodes = set()
                    target_nodes = set()
                    for record in records:
                        source = str(record['source_id'])
                        target = str(record['target_id'])
                        rel_type = record['relationship_type']
                        
                        source_label = ':'.join(record['source_labels'])
                        target_label = ':'.join(record['target_labels'])
                        
                        # Create dictionaries for node properties
                        source_props = record['source_props'].copy()
                        target_props = record['target_props'].copy()
                        
                        # Ensure 'name' and 'label' are in the properties
                        source_props['name'] = source_props.get('name', source)
                        source_props['label'] = source_label
                        source_props['node_type'] = 'source'
                        
                        target_props['name'] = target_props.get('name', target)
                        target_props['label'] = target_label
                        target_props['node_type'] = 'target'
                        
                        # Add nodes with all properties
                        G.add_node(source, **source_props)
                        G.add_node(target, **target_props)
                        G.add_edge(source, target, relationship=rel_type)
                        
                        source_nodes.add(source)
                        target_nodes.add(target)

                    ax.clear()
                    pos = nx.spring_layout(G, k=0.9, iterations=50)
                    
                    node_colors = ['lightblue' if G.nodes[n]['node_type'] == 'source' else 'lightgreen' for n in G.nodes()]
                    
                    draggable_graph = DraggableGraph(fig, ax, G, pos, self.show_node_properties)
                    draggable_graph.nodes.set_facecolors(node_colors)

                    edge_labels = nx.get_edge_attributes(G, 'relationship')
                    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, ax=ax, font_size=7)

                    total_relationships = len(G.edges())

                    ax.set_title(f'{source_label} ({len(source_nodes)}) -[:{relationship_name}]-> {target_label}({len(target_nodes)})')
                    ax.axis('off')

                    self.G = G  # Store the graph for later use
                    
                    canvas.draw()
                    self.log_message("Relate", f"Graph updated with {len(source_nodes)} source nodes, {len(target_nodes)} target nodes, and {total_relationships} relationships of type: {relationship_name}", "INFO")

            except Exception as e:
                self.log_message("Relate", f"Error viewing relationships graphically: {str(e)}", "ERROR")
                raise

        # Create a Qt dialog to display the graph
        dialog = QDialog(self)
        dialog.setWindowTitle("Relationship Graph")
        layout = QVBoxLayout(dialog)

        # Create the initial figure and canvas
        fig, ax = plt.subplots(figsize=(12, 8))
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)

        # Add Cypher query display at the top
        query_display = QTextEdit()
        query_display.setReadOnly(True)
        query_display.setMaximumHeight(100)
        layout.addWidget(query_display)

        # Add buttons
        button_layout = QHBoxLayout()
        zoom_in_btn = QPushButton("Zoom In")
        zoom_out_btn = QPushButton("Zoom Out")
        more_nodes_btn = QPushButton("More Nodes (+5)")
        less_nodes_btn = QPushButton("Less Nodes (-5)")
        
        button_layout.addWidget(zoom_in_btn)
        button_layout.addWidget(zoom_out_btn)
        button_layout.addWidget(more_nodes_btn)
        button_layout.addWidget(less_nodes_btn)
        layout.addLayout(button_layout)

        dialog.resize(1000, 800)

        def zoom(factor):
            cur_xlim = ax.get_xlim()
            cur_ylim = ax.get_ylim()
            new_xlim = [x / factor for x in cur_xlim]
            new_ylim = [y / factor for y in cur_ylim]
            ax.set_xlim(new_xlim)
            ax.set_ylim(new_ylim)
            canvas.draw()

        zoom_in_btn.clicked.connect(lambda: zoom(0.8))
        zoom_out_btn.clicked.connect(lambda: zoom(1.2))
        more_nodes_btn.clicked.connect(lambda: update_graph(node_limit + 5))
        less_nodes_btn.clicked.connect(lambda: update_graph(max(5, node_limit - 5)))

        update_graph(node_limit)  # Initial graph update
        dialog.exec()
        
    def refresh_relationship_types(self):
        current_text = self.relationship_name_combo.currentText()
        self.relationship_name_combo.clear()
        self.relationship_name_combo.addItems(self.get_relationship_types())
        if current_text in self.get_relationship_types():
            self.relationship_name_combo.setCurrentText(current_text)
        elif self.relationship_name_combo.count() > 0:
            self.relationship_name_combo.setCurrentIndex(0)


    def view_relationships(self):
        BASE_QUERY_TEMPLATE = """MATCH (source)-[r:`{}`]->(target)
        RETURN id(source) as source_id,
            id(target) as target_id,
            labels(source) as source_labels,
            labels(target) as target_labels,
            properties(source) as source_props,
            properties(target) as target_props,
            type(r) as relationship_type
        LIMIT {}"""

        relationship_name = self.relationship_name_combo.currentText()
        if not relationship_name:
            self.log_message("Relate", "Please select a relationship name", "ERROR")
            return

        limit = 10
        query = BASE_QUERY_TEMPLATE.format(relationship_name, limit)

        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query)
                records = list(result)
                
                if not records:
                    self.log_message("Relate", f"No relationships found for type: {relationship_name}", "INFO")
                else:
                    self.log_message("Relate", f"Displaying relationships of type: {relationship_name}", "INFO")
                    for record in records:
                        source_props = ", ".join([f"{k}: {v}" for k, v in record['source_props'].items()])
                        target_props = ", ".join([f"{k}: {v}" for k, v in record['target_props'].items()])
                        relationship_info = f"({':'.join(record['source_labels'])} {{{source_props}}}) -[:{record['relationship_type']}]-> ({':'.join(record['target_labels'])} {{{target_props}}})"
                        self.log_message("Relate", relationship_info, "INFO")
                
        except Exception as e:
            self.log_message("Relate", f"Error viewing relationships: {str(e)}", "ERROR")
            

    def update_cypher_query(self):
        source_label = self.source_label_combo.currentText()
        target_label = self.target_label_combo.currentText()
        relationship_name = self.relationship_name_combo.currentText()
        source_prop = self.source_props_list.currentItem().text() if self.source_props_list.currentItem() else None
        target_prop = self.target_props_list.currentItem().text() if self.target_props_list.currentItem() else None

        if all([source_label, target_label, relationship_name, source_prop, target_prop]):
            query = f"""
    MATCH (source:`{source_label}`)
    MATCH (target:`{target_label}`)
    WHERE source.`{source_prop}` = target.`{target_prop}`
    CREATE (source)-[r:`{relationship_name}`]->(target)
    RETURN count(r) as rel_count
    """
            self.cypher_query_edit.setPlainText(query.strip())
        else:
            self.cypher_query_edit.setPlainText("Select all required fields to generate Cypher query.")


    def update_source_property_colors(self):
        for i in range(self.source_props_list.count()):
            item = self.source_props_list.item(i)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
            item.setForeground(self.palette().text())

        selected_item = self.source_props_list.currentItem()
        if selected_item:
            font = selected_item.font()
            font.setBold(True)
            selected_item.setFont(font)
            selected_item.setForeground(QColor("blue"))


    def update_target_property_colors(self):
        for i in range(self.target_props_list.count()):
            item = self.target_props_list.item(i)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
            item.setForeground(self.palette().text())

        selected_item = self.target_props_list.currentItem()
        if selected_item:
            font = selected_item.font()
            font.setBold(True)
            selected_item.setFont(font)
            selected_item.setForeground(QColor("blue"))

   
    def update_target_property_colors(self):
        for i in range(self.target_props_list.count()):
            item = self.target_props_list.item(i)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
            item.setForeground(self.palette().text())  # Set to default text color

        selected_item = self.target_props_list.currentItem()
        if selected_item:
            font = selected_item.font()
            font.setBold(True)
            selected_item.setFont(font)
            selected_item.setForeground(QColor("green"))  # Set selected item to green

    def set_blue_text_color(self, list_widget):
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setForeground(QColor("blue"))

    def update_source_properties(self):
        label = self.source_label_combo.currentText()
        self.update_properties(label, self.source_props_list, self.source_props_table, is_source=True)

    def update_target_properties(self):
        label = self.target_label_combo.currentText()
        self.update_properties(label, self.target_props_list, self.target_props_table, is_source=False)

    def update_properties(self, label, props_list, props_table, is_source):
        if not label or self.neo4j_driver is None:
            props_list.clear()
            props_table.setRowCount(0)
            props_table.setColumnCount(0)
            return

        try:
            properties = self.get_label_properties(label)
            props_list.clear()
            props_list.addItems(properties)
            
            self.clear_property_selection(props_list, props_table)

            query = f"""
            MATCH (n:`{label}`)
            RETURN n
            LIMIT 100
            """

            with self.neo4j_driver.session() as session:
                result = session.run(query)
                data = [dict(record["n"]) for record in result]

            props_table.setRowCount(len(data))
            props_table.setColumnCount(len(properties))
            props_table.setHorizontalHeaderLabels(properties)

            for i, node in enumerate(data):
                for j, prop in enumerate(properties):
                    value = node.get(prop, "")
                    props_table.setItem(i, j, QTableWidgetItem(str(value)))

            props_table.resizeColumnsToContents()

            # Color matching properties
            self.color_matching_properties(is_source)

        except Exception as e:
            self.log_message("Neo4j", f"Error fetching property values: {str(e)}", "ERROR")
            props_list.clear()
            props_table.setRowCount(0)
            props_table.setColumnCount(0)

    def color_matching_properties(self, is_source):
        source_label = self.source_label_combo.currentText()
        target_label = self.target_label_combo.currentText()

        if source_label != target_label:
            source_props = set(self.source_props_list.item(i).text() for i in range(self.source_props_list.count()))
            target_props = set(self.target_props_list.item(i).text() for i in range(self.target_props_list.count()))
            
            common_props = source_props.intersection(target_props)
            
            color_map = {}
            for prop in common_props:
                color_map[prop] = self.generate_random_color()
            
            self.color_property_list(self.source_props_list, color_map)
            self.color_property_list(self.target_props_list, color_map)
        else:
            # Reset colors if labels are the same
            self.reset_property_colors(self.source_props_list)
            self.reset_property_colors(self.target_props_list)

    def color_property_list(self, props_list, color_map):
        for i in range(props_list.count()):
            item = props_list.item(i)
            prop = item.text()
            if prop in color_map:
                item.setForeground(color_map[prop])
            else:
                item.setForeground(self.palette().text())

    def reset_property_colors(self, props_list):
        for i in range(props_list.count()):
            item = props_list.item(i)
            item.setForeground(self.palette().text())
            
    def focus_source_property(self):
        self.focus_property(self.source_props_list, self.source_props_table)

    def focus_target_property(self):
        self.focus_property(self.target_props_list, self.target_props_table)

    def focus_property(self, props_list, props_table):
        selected_items = props_list.selectedItems()
        if not selected_items:
            return

        selected_property = selected_items[0].text()
        for col in range(props_table.columnCount()):
            if props_table.horizontalHeaderItem(col).text() == selected_property:
                props_table.setCurrentCell(0, col)  # Select the first cell in the column
                props_table.scrollToItem(props_table.item(0, col))  # Scroll to the selected cell
                props_table.selectColumn(col)
                break
            

    def clear_property_selection(self, props_list, props_table):
        props_list.clearSelection()
        props_table.clearSelection()


    def check_neo4j_connection(self):
        if self.neo4j_driver is None:
            self.log_message("Neo4j", "Not connected to Neo4j. Please connect first.", "WARN")
            self.create_rel_button.setEnabled(False)
            self.source_props_table.setRowCount(0)
            self.source_props_table.setColumnCount(0)
            self.target_props_table.setRowCount(0)
            self.target_props_table.setColumnCount(0)
        else:
            self.create_rel_button.setEnabled(True)
            self.populate_label_combos()
            self.update_source_properties()
            self.update_target_properties()



    def populate_label_combos(self):
        if self.neo4j_driver is None:
            self.log_message("Neo4j", "Not connected to Neo4j. Please connect first.", "ERROR")
            return
        
        try:
            labels = self.get_neo4j_labels()
            self.source_label_combo.addItems(labels)
            self.target_label_combo.addItems(labels)
        except Exception as e:
            self.log_message("Neo4j", f"Error fetching labels: {str(e)}", "ERROR")


    def update_source_props_table(self):
        self.update_props_table(self.source_label_combo.currentText(), 
                                self.source_props_list.currentItem().text() if self.source_props_list.currentItem() else None, 
                                self.source_props_table)

    def update_target_props_table(self):
        self.update_props_table(self.target_label_combo.currentText(), 
                                self.target_props_list.currentItem().text() if self.target_props_list.currentItem() else None, 
                                self.target_props_table)

    def update_props_table(self, label, property, table):
        if not label or not property or self.neo4j_driver is None:
            table.setRowCount(0)
            return

        query = f"""
        MATCH (n:`{label}`)
        WHERE n.`{property}` IS NOT NULL
        RETURN DISTINCT n.`{property}` AS value
        LIMIT 100
        """

        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query)
                data = [record["value"] for record in result]

            table.setRowCount(len(data))
            table.setColumnCount(1)
            table.setHorizontalHeaderLabels([property])

            for i, value in enumerate(data):
                table.setItem(i, 0, QTableWidgetItem(str(value)))

            table.resizeColumnsToContents()
        except Exception as e:
            self.log_message("Neo4j", f"Error fetching property values: {str(e)}", "ERROR")
            table.setRowCount(0)

    def get_label_properties(self, label):
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(f"MATCH (n:`{label}`) RETURN keys(n) AS props LIMIT 1")
                properties = result.single()['props']
            return properties
        except Exception as e:
            self.log_message("Neo4j", f"Error getting label properties: {str(e)}", "ERROR")
            return []


    def refresh_relationship_types(self):
        current_text = self.relationship_name_combo.currentText()
        self.relationship_name_combo.clear()
        self.relationship_name_combo.addItems(self.get_relationship_types())
        if current_text in self.get_relationship_types():
            self.relationship_name_combo.setCurrentText(current_text)
        elif self.relationship_name_combo.count() > 0:
            self.relationship_name_combo.setCurrentIndex(0)


    def show_node_properties(self, node):
        properties = self.G.nodes[node]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Node Properties: {properties['label']} {properties['name']}")
        layout = QVBoxLayout()
        
        for key, value in properties.items():
            label = QLabel(f"{key}: {value}")
            layout.addWidget(label)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)
        
        dialog.setLayout(layout)
        dialog.exec()
        

    def create_relationships(self):
        query = self.cypher_query_edit.toPlainText()

        if not query or query == "Select all required fields to generate Cypher query.":
            self.log_message("Relate", "Please provide a valid Cypher query", "ERROR")
            return

        self.relate_progress_bar.setValue(0)  # Reset progress bar

        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query)
                records = list(result)  # Consume all records
                summary = result.consume()
                
                # Check if the query returns a 'rel_count'
                if records and 'rel_count' in records[0]:
                    rel_count = records[0]['rel_count']
                else:
                    # If not, we'll use the number of relationships created from the summary
                    rel_count = summary.counters.relationships_created
                
                self.log_message("Relate", f"Created {rel_count} relationships", "INFO")
                
                # After creating relationships, refresh the relationship types
                self.refresh_relationship_types()
                
                # After creating relationships, automatically view them
                self.view_relationships()
        except Exception as e:
            self.log_message("Relate", f"Error creating relationships: {str(e)}", "ERROR")
        finally:
            self.relate_progress_bar.setValue(100)

if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, '')
    app = QApplication(sys.argv)
    app.setApplicationName("Graph Migrate")
    app.setApplicationDisplayName("Graph Migrate")
    app.setApplicationVersion("1.0")
    
    m = Migrate()
    m.show()
    sys.exit(app.exec())                 
                                         