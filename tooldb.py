#!/usr/bin/env python3

from qtpy.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QLabel, QHBoxLayout, QMessageBox, QStackedWidget, QFormLayout, QTextEdit, QComboBox, QProgressDialog,
    QCompleter, QAbstractItemView
)
from qtpy.QtCore import Qt, QTimer, QUrl, QStringListModel
from qtpy.QtGui import QGuiApplication, QIcon, QDesktopServices, QPixmap

from gentoolwiki import (
    delete_wiki_item, main as wiki_main, generate_index_page_content,
    upload_wiki_page, generate_tools_json
)
import re
import time
import sqlite3
from settings import load_config

# Load the configuration
config = load_config()
class FilterableComboBox(QComboBox):
    def __init__(self, get_items_callback, parent=None):
        """
        A combo box that dynamically filters its items and preserves proper behavior on focus and selection.

        Args:
            get_items_callback (callable): A function that retrieves items dynamically.
        """
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(10)

        self.get_items_callback = get_items_callback

        self.completer = QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)

        self.line_edit = self.lineEdit()
        self.line_edit.setCompleter(self.completer)

        self.line_edit.textEdited.connect(self.filter_items)
        self.completer.activated.connect(self.on_completer_activated)

        self.model = QStringListModel()
        self.completer.setModel(self.model)

        self.last_items = []

    def set_items(self, items):
        """
        Populate the combo box with items.
        """
        self.clear()
        self.addItem("")  # Add blank entry
        self.addItems(items)
        self.model.setStringList([""] + items)
        self.last_items = items

    def filter_items(self, text):
        """
        Filter items based on input text.
        """
        filtered_items = [item for item in self.last_items if text.lower() in item.lower()]
        self.model.setStringList([""] + filtered_items)

    def on_completer_activated(self, text):
        """
        Set the selected text in the line edit.
        """
        self.setEditText(text)

    def set_selected_value(self, value):
        """
        Set the combo box's selected value explicitly.

        Args:
            value (str): The value to set in the combo box.
        """
        # Ensure the dropdown is updated with the latest items
        items = self.get_items_callback()
        if items != self.last_items:
            self.set_items(items)

        # Find the value in the dropdown and set it
        index = self.findText(value, Qt.MatchFixedString)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            self.setEditText(value)  # Allow for custom or unmatched values

    def focusInEvent(self, event):
        """
        Refresh items when focused.
        """
        items = self.get_items_callback()
        if items != self.last_items:
            self.set_items(items)

        self.line_edit.selectAll()
        super().focusInEvent(event)


class DatabaseManager:
    def __init__(self, db_path="tools.db"):
        self.db_path = db_path
        self.connection = sqlite3.connect(self.db_path)

    def fetch_all(self):
        with self.connection:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT ToolNumber, ToolName, ToolType, Shape, ToolShankSize, Flutes, OAL, LOC,
                    ToolMaxRPM, ToolDiameter, ToolMaterial, ToolCoating, PartNumber,
                    ManufacturerName, ToolOrderURL, Materials, SuggestedRPM,
                    SuggestedMaxDOC, AdditionalNotes, SuggestedFeedRate, ToolImageFileName,
                    Chipload, TipAngle, CuttingEdgeAngle, TipDiameter, TorusRadius,
                    ShaftDiameter, SpindleDirection, SpindlePower, BladeThickness,
                    CapDiameter, CapHeight, Stickout, CuttingRadius
                FROM tools
            """)
            columns = [description[0] for description in cursor.description]
            data = cursor.fetchall()
        return data, columns

    def fetch_filtered(self, keyword):
        with self.connection:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT ToolNumber, ToolName, ToolType, Shape, ToolShankSize, Flutes, OAL, LOC, ToolMaxRPM, ToolDiameter,
                    ToolMaterial, ToolCoating, PartNumber, ManufacturerName, ToolOrderURL, Materials, SuggestedRPM,
                    SuggestedMaxDOC, AdditionalNotes, SuggestedFeedRate, ToolImageFileName, Chipload, TipAngle,
                    CuttingEdgeAngle, TipDiameter, TorusRadius, ShaftDiameter, SpindleDirection, SpindlePower,
                    BladeThickness, CapDiameter, CapHeight, Stickout, CuttingRadius
                FROM tools
                WHERE ToolName LIKE ?
                OR ToolType LIKE ?
                OR ToolNumber LIKE ?
                OR ManufacturerName LIKE ?
            """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))

            # Retrieve column names dynamically
            columns = [description[0] for description in cursor.description]
            data = cursor.fetchall()
        return data, columns


    def fetch_shapes(self):
        """Fetch all shapes from the FCShapes table."""
        with self.connection:
            rows = self.connection.execute("SELECT ShapeName FROM FCShapes ORDER BY ShapeName").fetchall()
            return [row[0] for row in rows]

    def insert(self, data):
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO tools (
                    ToolNumber, ToolName, ToolType, Shape, ToolShankSize, Flutes, OAL, LOC, ToolMaxRPM,
                    ToolDiameter, ToolMaterial, ToolCoating, PartNumber, ManufacturerName, ToolOrderURL,
                    Materials, SuggestedRPM, SuggestedMaxDOC, AdditionalNotes, SuggestedFeedRate,
                    ToolImageFileName, Chipload, TipAngle, CuttingEdgeAngle, TipDiameter, TorusRadius,
                    ShaftDiameter, SpindleDirection, SpindlePower, BladeThickness, CapDiameter, CapHeight, Stickout, CuttingRadius
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                data,
            )

    def update(self, tool_number, data):
        with self.connection:
            self.connection.execute(
                """
                UPDATE tools SET
                    ToolName = ?, ToolType = ?, Shape = ?, ToolShankSize = ?, Flutes = ?, OAL = ?, LOC = ?,
                    ToolMaxRPM = ?, ToolDiameter = ?, ToolMaterial = ?, ToolCoating = ?, PartNumber = ?,
                    ManufacturerName = ?, ToolOrderURL = ?, Materials = ?, SuggestedRPM = ?, SuggestedMaxDOC = ?,
                    AdditionalNotes = ?, SuggestedFeedRate = ?, ToolImageFileName = ?, Chipload = ?,
                    TipAngle = ?, CuttingEdgeAngle = ?, TipDiameter = ?, TorusRadius = ?, ShaftDiameter = ?,
                    SpindleDirection = ?, SpindlePower = ?, BladeThickness = ?, CapDiameter = ?, CapHeight = ?,
                    Stickout = ?, CuttingRadius = ?
                    WHERE ToolNumber = ?
                """,
                data + [tool_number],
            )

    def delete(self, tool_number):
        with self.connection:
            self.connection.execute("DELETE FROM tools WHERE ToolNumber = ?", (tool_number,))

class ToolDatabaseGUI(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.confg = config

        # Initialize the debounce timer for search
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)  # Ensure the timer only triggers once after reset
        self.search_timer.timeout.connect(self.perform_search)

        # Initialize database connection
        self.db = DatabaseManager()

        self.setWindowTitle("OpenBitLib - Toolbit Database Manager")

        # Parse window size and position
        window_size = config.get("gui_settings", {}).get("default_window_size", "1559x780")
        window_position = config.get("gui_settings", {}).get("default_window_position", "0x0")
        width, height = map(int, window_size.split('x'))
        x, y = map(int, window_position.split('x'))
        self.setGeometry(x, y, width, height)

        self.setWindowFlags(Qt.Window)

        # Set theme dynamically
        theme = config.get("gui_settings", {}).get("theme", "Fusion")
        QApplication.setStyle(theme)

        # Define shape fields dynamically
        self.shape_fields = config.get("tool_settings", {}).get("shape_fields", {
            "endmill.fcstd": ["Chipload", "CuttingEdgeHeight", "SpindleDirection", "Stickout"],
            "ballend.fcstd": ["Chipload", "CuttingEdgeHeight", "Stickout"],
            "v-bit.fcstd": ["CuttingEdgeAngle", "TipDiameter", "CuttingEdgeHeight", "Stickout"],
            "torus.fcstd": ["TorusRadius", "CuttingEdgeHeight", "Chipload", "SpindleDirection", "Stickout"],
            "drill.fcstd": ["TipAngle", "Chipload", "Stickout"],
            "slittingsaw.fcstd": ["BladeThickness", "CapDiameter", "CapHeight"],
            "probe.fcstd": ["ShaftDiameter", "SpindlePower"],
            "roundover.fcstd": ["CuttingRadius","CuttingEdgeHeight", "TipDiameter","Chipload", "Stickout"],
        })

        # Fields to format dynamically
        self.fields_to_format = config.get("tool_settings", {}).get("fields_to_format", {
            "SuggestedMaxDOC": "dimension",
            "ToolShankSize": "dimension",
            "OAL": "dimension",
            "LOC": "dimension",
            "ToolDiameter": "dimension",
            "Chipload": "dimension",
            "TipDiameter": "dimension",
            "TorusRadius": "dimension",
            "ShaftDiameter": "dimension",
            "BladeThickness": "dimension",
            "CapDiameter": "dimension",
            "CapHeight": "dimension",
            "CuttingEdgeAngle": "angle",
            "TipAngle": "angle",
            "ToolMaxRPM": "rpm",
            "ToolNumber": "number",
            "Flutes": "number",
            "Stickout": "dimension",
            "CuttingRadius": "dimension",
        })

        self.COLUMN_LABELS = {
            "ToolNumber": "Tool Number",
            "ToolName": "Tool Name",
            "ToolType": "Tool Type",
            "Shape": "Shape",
            "ToolShankSize": "Shank Size",
            "Flutes": "Flutes",
            "OAL": "Overall Length",
            "LOC": "Length of Cut",
            "ToolMaxRPM": "Max RPM",
            "ToolDiameter": "Diameter",
            "ToolMaterial": "Material",
            "ToolCoating": "Coating",
            "PartNumber": "Part Number",
            "ManufacturerName": "Manufacturer",
            "ToolOrderURL": "Order Link",
            "Materials": "Materials",
            "SuggestedRPM": "Suggested RPM",
            "SuggestedMaxDOC": "Max Depth of Cut",
            "AdditionalNotes": "Notes",
            "SuggestedFeedRate": "Feed Rate",
            "ToolImageFileName": "Image File",
            "Chipload": "Chipload",
            "TipAngle": "Tip Angle",
            "CuttingEdgeAngle": "Cutting Edge Angle",
            "TipDiameter": "Tip Diameter",
            "TorusRadius": "Torus Radius",
            "ShaftDiameter": "Shaft Diameter",
            "SpindleDirection": "Spindle Direction",
            "SpindlePower": "Spindle Power",
            "BladeThickness": "Blade Thickness",
            "CapDiameter": "Cap Diameter",
            "CapHeight": "Cap Height",
            "Stickout": "Stickout",
            "CuttingRadius": "Cutting Radius",
        }

        # Define column names
        self.column_names = [
            "ToolNumber", "ToolName", "ToolType", "Shape", "ToolShankSize", "Flutes", "OAL",
            "LOC", "ToolMaxRPM", "ToolDiameter", "ToolMaterial", "ToolCoating", "PartNumber",
            "ManufacturerName", "ToolOrderURL", "Materials", "SuggestedRPM", "SuggestedMaxDOC",
            "AdditionalNotes", "SuggestedFeedRate", "ToolImageFileName", "Chipload", "TipAngle",
            "CuttingEdgeAngle", "TipDiameter", "TorusRadius", "ShaftDiameter", "SpindleDirection",
            "SpindlePower", "BladeThickness", "CapDiameter", "CapHeight", "Stickout","CuttingRadius",
        ]

        # Initialize UI components
        self.tool_inputs = {}

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout()
        self.central_widget.setLayout(self.layout)

        # Initialize search bar, table, and form
        self.search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tools by name or type...")
        self.search_input.returnPressed.connect(self.search_tools)
        self.search_input.textChanged.connect(self.search_tools)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_tools)
        self.search_layout.addWidget(self.search_input)
        self.search_layout.addWidget(self.search_button)
        self.layout.addLayout(self.search_layout)

        # Table
        self.table = QTableWidget()
        self.table.setMinimumHeight(self.table.verticalHeader().defaultSectionSize() * 4)
        self.table.itemClicked.connect(self.load_tool_into_form)
        self.table.setSortingEnabled(True)
        self.layout.addWidget(self.table)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Stacked Widget for Pages
        self.stacked_widget = QStackedWidget()
        self.layout.addWidget(self.stacked_widget)

        # Define fields from the original table
        self.page1_fields = {
#            "ToolNumber": {"label": self.COLUMN_LABELS["ToolNumber"], "widget": QLineEdit(), "column": "left", "width": 100},
            "ToolNumber": {"label": self.COLUMN_LABELS["ToolNumber"], "widget": self.create_url_widget(100, generate_url_callback=lambda tool_number: f"https://wiki.knoxmakers.org/Nibblerbot/tools/tool_{tool_number}" if tool_number else ""), "column": "left", "width": 100 },
            "ToolName": {"label": self.COLUMN_LABELS["ToolName"], "widget": QLineEdit(), "column": "left", "width": 350},
            "ToolType": {"label": self.COLUMN_LABELS["ToolType"], "widget": QLineEdit(), "column": "left", "width": 350},
            "ToolShankSize": {"label": self.COLUMN_LABELS["ToolShankSize"], "widget": QLineEdit(), "column": "left", "width": 150},
            "ToolDiameter": {"label": self.COLUMN_LABELS["ToolDiameter"], "widget": QLineEdit(), "column": "left", "width": 150},
            "Flutes": {"label": self.COLUMN_LABELS["Flutes"], "widget": QLineEdit(), "column": "left", "width": 100},
            "OAL": {"label": self.COLUMN_LABELS["OAL"], "widget": QLineEdit(), "column": "left", "width": 150},
            "LOC": {"label": self.COLUMN_LABELS["LOC"], "widget": QLineEdit(), "column": "left", "width": 150},
            "ToolMaxRPM": {"label": self.COLUMN_LABELS["ToolMaxRPM"], "widget": QLineEdit(), "column": "left", "width": 150},
            "ToolMaterial": {"label": self.COLUMN_LABELS["ToolMaterial"], "widget": QComboBox(), "column": "left", "width": 150},
            "ToolCoating": {"label": self.COLUMN_LABELS["ToolCoating"], "widget": self.create_filterable_combobox("ToolCoating"), "column": "left", "width": 150},
            "ToolImageFileName": {"label": self.COLUMN_LABELS["ToolImageFileName"], "widget": QLineEdit(), "column": "left", "width": 200},
            "SuggestedMaxDOC": {"label": self.COLUMN_LABELS["SuggestedMaxDOC"], "widget": QLineEdit(), "column": "right", "width": 150},
            "SuggestedRPM": {"label": self.COLUMN_LABELS["SuggestedRPM"], "widget": QLineEdit(), "column": "right", "width": 300},
            "PartNumber": {"label": self.COLUMN_LABELS["PartNumber"], "widget": QLineEdit(), "column": "right", "width": 300},
            "ManufacturerName": {"label": self.COLUMN_LABELS["ManufacturerName"], "widget": self.create_filterable_combobox("ManufacturerName"), "column": "right", "width": 500},
            "ToolOrderURL": { "label": self.COLUMN_LABELS["ToolOrderURL"], "widget": self.create_url_widget(500), "column": "right", "width": 500 },
            "Materials": {"label": self.COLUMN_LABELS["Materials"], "widget": QTextEdit(), "column": "right", "width": 500, "height": 70},
            "AdditionalNotes": {"label": self.COLUMN_LABELS["AdditionalNotes"], "widget": QTextEdit(), "column": "right", "width": 500, "height": 70},
            "SuggestedFeedRate": {"label": self.COLUMN_LABELS["SuggestedFeedRate"], "widget": QTextEdit(), "column": "right", "width": 500, "height": 70},
        }

        # Page 1: Basic Tool Info
        self.page1 = QWidget()
        self.page1_layout = QHBoxLayout()  # Use QHBoxLayout for two main columns
        self.page1.setLayout(self.page1_layout)

        # Left and Right Columns
        self.left_form_layout = QFormLayout()
        self.right_form_layout = QFormLayout()
        self.page1_layout.addLayout(self.left_form_layout)
        self.page1_layout.addLayout(self.right_form_layout)

        # Configure alignment and spacing for both columns
        self.left_form_layout.setLabelAlignment(Qt.AlignLeft)  # Align labels to the left
        self.left_form_layout.setFormAlignment(Qt.AlignLeft)  # Align fields to the left
        self.left_form_layout.setHorizontalSpacing(20)  # Space between labels and fields
        self.left_form_layout.setVerticalSpacing(10)  # Space between rows

        self.right_form_layout.setLabelAlignment(Qt.AlignLeft)  # Align labels to the left
        self.right_form_layout.setFormAlignment(Qt.AlignLeft)  # Align fields to the left
        self.right_form_layout.setHorizontalSpacing(20)
        self.right_form_layout.setVerticalSpacing(10)

        # Add fields to their respective columns
        for field, config in self.page1_fields.items():
            label = QLabel(config["label"])
            input_field = config["widget"]

            # Ensure the widget is added to self.tool_inputs for later access
            self.tool_inputs[field] = input_field
            # Connect formatting for specific fields
            if field in self.fields_to_format:
                if isinstance(input_field, QLineEdit):  # Only connect if it's a QLineEdit
                    input_field.editingFinished.connect(
                        lambda name=field: self.format_field(name)
                    )
                elif isinstance(input_field, QTextEdit):  # Handle QTextEdit differently
                    input_field.textChanged.connect(
                        lambda: self.format_field(field)
                    )

            # Apply width and height
            if "width" in config:
                input_field.setFixedWidth(config["width"])
            if "height" in config and isinstance(input_field, QTextEdit):
                input_field.setFixedHeight(config["height"])

            # Add the label-field pair to the appropriate column's QFormLayout
            if config["column"] == "left":
                self.left_form_layout.addRow(label, input_field)
            elif config["column"] == "right":
                self.right_form_layout.addRow(label, input_field)

        # Adjust the main layout spacing and margins
        self.page1_layout.setSpacing(50)  # Space between left and right columns
        self.page1_layout.setContentsMargins(10, 10, 10, 10)  # Outer margins

        # Populate the 'ToolMaterial' combo box
        if "ToolMaterial" in self.tool_inputs and isinstance(self.tool_inputs["ToolMaterial"], QComboBox):
            self.tool_inputs["ToolMaterial"].clear()
            self.tool_inputs["ToolMaterial"].addItems(["Carbide", "HSS"])

        self.stacked_widget.addWidget(self.page1)

        # Hardcoded page2 fields
        self.page2 = QWidget()
        self.page2_layout = QFormLayout()
        self.page2.setLayout(self.page2_layout)

        # Page 2: Advanced Tool Info
        self.page2 = QWidget()
        self.page2_layout = QFormLayout()
        self.page2.setLayout(self.page2_layout)
        self.page2_fields = {
            "Shape": {"label": self.COLUMN_LABELS["Shape"], "widget": QComboBox(), "width": 200},
            "Stickout": {"label": self.COLUMN_LABELS["Stickout"], "widget": QLineEdit(), "width": 150},
            "Chipload": {"label": self.COLUMN_LABELS["Chipload"], "widget": QLineEdit(), "width": 150},
            "TipAngle": {"label": self.COLUMN_LABELS["TipAngle"], "widget": QLineEdit(), "width": 150},
            "CuttingEdgeAngle": {"label": self.COLUMN_LABELS["CuttingEdgeAngle"], "widget": QLineEdit(), "width": 150},
            "TipDiameter": {"label": self.COLUMN_LABELS["TipDiameter"], "widget": QLineEdit(), "width": 150},
            "TorusRadius": {"label": self.COLUMN_LABELS["TorusRadius"], "widget": QLineEdit(), "width": 150},
            "ShaftDiameter": {"label": self.COLUMN_LABELS["ShaftDiameter"], "widget": QLineEdit(), "width": 150},
            "SpindleDirection": {"label": self.COLUMN_LABELS["SpindleDirection"], "widget": QLineEdit(), "width": 150},
            "SpindlePower": {"label": self.COLUMN_LABELS["SpindlePower"], "widget": QLineEdit(), "width": 150},
            "BladeThickness": {"label": self.COLUMN_LABELS["BladeThickness"], "widget": QLineEdit(), "width": 150},
            "CapDiameter": {"label": self.COLUMN_LABELS["CapDiameter"], "widget": QLineEdit(), "width": 150},
            "CapHeight": {"label": self.COLUMN_LABELS["CapHeight"], "widget": QLineEdit(), "width": 150},
            "CuttingRadius": {"label": self.COLUMN_LABELS["CuttingRadius"], "widget": QLineEdit(), "width": 150},
        }

        for field, config in self.page2_fields.items():
            label = QLabel(config["label"])
            input_field = config["widget"]
            input_field.setMaximumWidth(config["width"])

            # Apply maximum height if specified in the config
            if "height" in config:
                input_field.setMaximumHeight(config["height"])

            self.tool_inputs[field] = input_field
            self.page2_layout.addRow(label, input_field)

            # Connect formatting for specific fields
            if field in self.fields_to_format:
                input_field.editingFinished.connect(
                    lambda name=field: self.format_field(name)
                )

        shapes = self.db.fetch_shapes()
        if "Shape" in self.tool_inputs and isinstance(self.tool_inputs["Shape"], QComboBox):
            self.tool_inputs["Shape"].clear()  # Clear existing items
            self.tool_inputs["Shape"].addItems(shapes)
            self.tool_inputs["Shape"].currentTextChanged.connect(self.update_fields_visibility)

        self.stacked_widget.addWidget(self.page2)

        # Navigation Buttons
        self.nav_layout = QHBoxLayout()
        self.page1_button = QPushButton("Basic Info")
        self.page1_button.clicked.connect(lambda: self.stacked_widget.setCurrentWidget(self.page1))
        self.page2_button = QPushButton("FreeCAD Parameters")
        self.page2_button.clicked.connect(lambda: self.stacked_widget.setCurrentWidget(self.page2))
        self.nav_layout.addWidget(self.page1_button)
        self.nav_layout.addWidget(self.page2_button)
        self.layout.addLayout(self.nav_layout)

        # Buttons
        self.button_layout = QHBoxLayout()

        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.add_tool)
        self.button_layout.addWidget(self.add_button)

        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.update_tool)
        self.button_layout.addWidget(self.update_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_tool)
        self.button_layout.addWidget(self.delete_button)

        self.publish_all_button = QPushButton("Publish All Tools")
        self.publish_all_button.clicked.connect(self.publish_all_tools)
        self.button_layout.addWidget(self.publish_all_button)

        self.layout.addLayout(self.button_layout)

        self.load_data()
        self.add_tool(from_init=True)


    def create_url_widget(self, total_width, generate_url_callback=None):
        """
        Create a widget containing a QLineEdit for URL input and a QPushButton to open the URL.

        Parameters:
        - total_width: The total width of the widget.
        - generate_url_callback: An optional callback function to dynamically generate the URL
        based on the text input. This callback should accept the text input and return a URL.
        """
        button_width = 30  # Width of the button
        spacing = 5  # Optional spacing between the text field and button

        # Calculate the adjusted width for the QLineEdit
        adjusted_width = total_width - button_width - spacing

        # Create the layout for the widget
        url_layout = QHBoxLayout()
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(spacing)

        # QLineEdit for URL input
        url_input = QLineEdit()
        url_input.setFixedWidth(adjusted_width)  # Set the adjusted width
        url_input.setFixedHeight(28)
        url_layout.addWidget(url_input)

        # Add a button to open the URL
        open_url_button = QPushButton()
        open_url_button.setIcon(QIcon("icons/external-link.svg"))  # Replace with your icon's path
        open_url_button.setMaximumWidth(button_width)
        open_url_button.setMaximumHeight(button_width)
        url_layout.addWidget(open_url_button)

        # Create a container widget for the layout
        container_widget = QWidget()
        container_widget.setLayout(url_layout)
        container_widget.setFixedHeight(28)
        open_url_button.setEnabled(False)  # Initially disabled

        # Variable to store the URL for this widget
        widget_url = None

        # Function to handle text changes
        def handle_text_changed(text):
            nonlocal widget_url
            # Use the callback to generate the URL, or default to the input text
            if generate_url_callback:
                widget_url = generate_url_callback(text.strip())
            else:
                widget_url = text.strip()

            # Enable the button only if there's a valid URL
            open_url_button.setEnabled(bool(widget_url))

        # Connect QLineEdit's textChanged signal to handle text updates
        url_input.textChanged.connect(handle_text_changed)

        # Connect the button click to open the correct URL
        open_url_button.clicked.connect(lambda: self.open_url_in_browser(widget_url))

        return container_widget

    def open_url_in_browser(self, url):
        """
        Open the specified URL in the user's default web browser.
        """
        if url.strip():
            QDesktopServices.openUrl(QUrl(url))
        #else:
        #    QMessageBox.warning(self, "Invalid URL", "The URL field is empty or invalid.")


    def setup_table(self):
        """Setup the data table."""
        self.table = QTableWidget()
        self.table.setMinimumHeight(self.table.verticalHeader().defaultSectionSize() * 7)
        self.table.itemClicked.connect(self.load_tool_into_form)

        # Set column headers dynamically
        headers = [self.COLUMN_LABELS.get(col, col) for col in self.column_names]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.layout.addWidget(self.table)

    def update_fields_visibility(self):
        """
        Show or hide fields and their labels based on the selected shape.
        """
        selected_shape = self.tool_inputs["Shape"].currentText()

        # Common fields that are always visible
        always_visible_fields = set([
            "ToolNumber", "ToolName", "ToolType", "Shape", "ToolShankSize", "Flutes",
            "OAL", "LOC", "ToolMaxRPM", "ToolDiameter", "ToolMaterial", "ToolCoating",
            "PartNumber", "ManufacturerName", "ToolOrderURL", "Materials", "SuggestedRPM",
            "SuggestedMaxDOC", "AdditionalNotes", "SuggestedFeedRate", "ToolImageFileName"
        ])

        # Fields specific to the selected shape
        specific_fields = set(self.shape_fields.get(selected_shape, []))

        # Update visibility for page1 fields
        #self.update_page_fields_visibility(self.page1_layout, always_visible_fields, specific_fields)

        # Update visibility for page2 fields
        self.update_page_fields_visibility(self.page2_layout, always_visible_fields, specific_fields)

    def update_page_fields_visibility(self, layout, always_visible_fields, specific_fields):
        """
        Update visibility for fields in a specific page layout.
        """
        for i in range(layout.rowCount()):
            label_widget = layout.itemAt(i, QFormLayout.LabelRole).widget()
            field_widget = layout.itemAt(i, QFormLayout.FieldRole).widget()

            for field_name, widget in self.tool_inputs.items():
                if field_widget == widget:
                    if field_name in always_visible_fields or field_name in specific_fields:
                        field_widget.show()
                        if label_widget:
                            label_widget.show()
                    else:
                        field_widget.hide()
                        if label_widget:
                            label_widget.hide()

    def format_field(self, field_name):
        """
        Format the value of a form field based on its type.

        Applies specific formatting rules for dimensions, angles, RPMs, or 
        numbers based on the field's type. Handles units, precision, and 
        validation dynamically.

        Args:
            field_name (str): The name of the field to be formatted.
        """
        widget = self.tool_inputs[field_name]
        value = widget.text().strip()

        if not value:
            return  # Do nothing for empty inputs

        field_type = self.fields_to_format.get(field_name, "text")

        try:
            if field_type == "dimension":
                # Normalize input and detect units for dimensions
                if value.upper() == "N/A":
                    widget.setText("N/A")  # Allow "N/A" as a valid input for dimensions
                    return

                match = re.match(r"([\d.]+)\s*([a-zA-Z\"']*)", value)
                if match:
                    number_str, unit = match.groups()
                    number = float(number_str)

                    # Handle recognized units
                    if unit in ('', '"', 'in'):
                        imperial_precision = config["tool_settings"].get("imperial_precision", 4)
                        formatted_value = f"{number:.{imperial_precision}f} in"
                    elif unit.lower() in ('mm', 'millimeter'):
                        metric_precision = config["tool_settings"].get("metric_precision", 3)
                        formatted_value = f"{number:.{metric_precision}f} mm"
                    else:
                        # For unrecognized units, strip invalid part and default to inches
                        imperial_precision = config["tool_settings"].get("imperial_precision", 4)
                        formatted_value = f"{number:.{imperial_precision}f} in"

                    widget.setText(formatted_value)
                else:
                    # If input doesn't match the expected pattern, clean the field
                    number = re.sub(r"[^\d.]", "", value)  # Remove all non-numeric characters
                    try:
                        number = float(number)  # Attempt to convert to float
                        imperial_precision = config["tool_settings"].get("imperial_precision", 4)
                        formatted_value = f"{number:.{imperial_precision}f} in"  # Default to inches
                        widget.setText(formatted_value)
                    except ValueError:
                        widget.clear()  # Clear field if conversion fails

            elif field_type == "angle":
                # Format angle fields with configurable precision
                angle_precision = config["tool_settings"].get("angle_precision", 4)
                number = re.sub(r"[^\d.]", "", value)  # Remove all non-digit and non-decimal characters
                if number:  # Ensure there is something to convert
                    formatted_value = f"{float(number):.{angle_precision}f} °"  # Apply precision
                    widget.setText(formatted_value)
                else:
                    widget.clear()  # Clear the field if it contains no valid number

            elif field_type == "rpm":
                # Format RPM fields
                if value == "-1":
                    widget.setText("-1")  # Allow -1 as a valid value
                    return
                number = re.sub(r"[^\d]", "", value)  # Remove all non-digit characters
                if number:  # Ensure there is something to convert
                    number = int(number)  # Convert the cleaned value to an integer
                    formatted_value = f"{number:,}"  # Format with commas
                    widget.setText(formatted_value)
                else:
                    widget.clear()  # Clear the field if it contains no valid number

            elif field_type == "number":
                if value.upper() == "N/A":
                    widget.setText("N/A")  # Allow "N/A" as a valid input for dimensions
                    return

                # Ensure numeric input only
                number = re.sub(r"[^\d]", "", value)  # Strip non-numeric characters
                widget.setText(number)

        except ValueError:
            QMessageBox.warning(self, "Invalid Input", f"Invalid format for {field_name}. Please enter a valid number.")

    def find_label_for_field(self, field_widget):
        """
        Find the label corresponding to a field widget across both page1 and page2.

        Args:
            field_widget (QWidget): The widget for which the label is to be found.

        Returns:
            QLabel: The label widget corresponding to the given field widget, or None if not found.
        """
        # Check page1 layout
        label = self.find_label_in_layout(self.page1_layout, field_widget)
        if label:
            return label

        # Check page2 layout
        label = self.find_label_in_layout(self.page2_layout, field_widget)
        return label

    def fetch_unique_column_values(self, column_name):
            """
            Fetch unique values for a given column from the tools table.

            Args:
                column_name (str): The name of the column.

            Returns:
                list: A list of unique values.
            """
            try:
                with sqlite3.connect(self.db.db_path) as connection:
                    cursor = connection.cursor()
                    query = f"SELECT DISTINCT {column_name} FROM tools WHERE {column_name} IS NOT NULL"
                    cursor.execute(query)
                    return [row[0] for row in cursor.fetchall()]
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Database Error", f"Failed to fetch {column_name} values: {e}")
                return []

    def create_filterable_combobox(self, column_name):
        """
        Create a FilterableComboBox for a specified database column.

        Args:
            column_name (str): The column to fetch unique values for.

        Returns:
            FilterableComboBox: The populated combo box.
        """
        def get_items():
            return self.fetch_unique_column_values(column_name)

        combobox = FilterableComboBox(get_items_callback=get_items)
        combobox.setFixedWidth(500)
        return combobox

    def find_label_in_layout(self, layout, field_widget):
        """
        Find the label for a field widget within a specific layout.

        Args:
            layout (QFormLayout): The layout to search for the field widget.
            field_widget (QWidget): The widget for which the label is to be found.

        Returns:
            QLabel: The label widget corresponding to the given field widget, or None if not found.
        """
        for i in range(layout.rowCount()):
            label_widget = layout.itemAt(i, QFormLayout.LabelRole).widget()
            field_in_layout = layout.itemAt(i, QFormLayout.FieldRole).widget()
            if field_in_layout == field_widget:
                return label_widget
        return None

    def load_data(self, data=None):
        """
        Populate the table widget with tool data.

        If no data is provided, fetches all tools from the database. Otherwise,
        populates the table with the provided data.

        Args:
            data (list of tuples, optional): Tool data to display in the table.
            Each tuple represents a row of tool data. Defaults to None.
        """
        if data is None:
            data, sql_columns = self.db.fetch_all()  # Fetch both data and column names
        else:
            sql_columns = self.column_names  # Assume provided data aligns with `self.column_names`

        # Columns to hide (but still load into the table)
        hidden_columns = {
            "ToolImageFileName", "Chipload", "TipAngle", "CuttingEdgeAngle", "TipDiameter",
            "TorusRadius", "ShaftDiameter", "SpindleDirection", "SpindlePower",
            "BladeThickness", "CapDiameter", "CapHeight"
        }

        # Columns that should not auto-resize
        no_resize_list = {"Materials","AdditionalNotes", "ToolOrderURL"}

        # Set headers and populate the table
        headers = [self.COLUMN_LABELS.get(col, col) for col in self.column_names]
        self.table.setRowCount(len(data))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        # Create a mapping of column indices
        sql_column_index = {col: idx for idx, col in enumerate(sql_columns)}

        # Populate the table
        for row_idx, row_data in enumerate(data):
            for col_idx, col_name in enumerate(self.column_names):
                value = row_data[sql_column_index[col_name]]
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value is not None else ""))

        # Hide specified columns
        for col_idx, col_name in enumerate(self.column_names):
            if col_name in hidden_columns:
                self.table.setColumnHidden(col_idx, True)

        # Adjust column widths
        for col_idx, col_name in enumerate(self.column_names):
            if col_name not in no_resize_list and col_name not in hidden_columns:
                self.table.resizeColumnToContents(col_idx)

    def load_tool_into_form(self, item):
        """
        Populate the form fields with the selected row data from the table.

        Args:
            item (QTableWidgetItem): The selected item from the table widget.
            Used to determine the corresponding row data.
        """
        row = item.row()

        # Map column names to data for the selected row
        row_data = {
            col_name: self.table.item(row, col_idx).text() if self.table.item(row, col_idx) else ""
            for col_idx, col_name in enumerate(self.column_names)
        }

        # Populate the input fields dynamically
        for field_name, widget in self.tool_inputs.items():
            value = row_data.get(field_name, "")

            # Check if the widget is a container with a layout
            if widget.layout():
                # Try to get the first widget in the layout (e.g., QLineEdit for custom widgets)
                inner_widget = widget.layout().itemAt(0).widget() if widget.layout().count() > 0 else None
                if isinstance(inner_widget, QLineEdit):
                    inner_widget.setText(value)
                elif isinstance(inner_widget, QTextEdit):
                    inner_widget.setPlainText(value)
            else:
                # Handle standard widgets
                if isinstance(widget, FilterableComboBox):
                    widget.set_selected_value(value)
                elif isinstance(widget, QLineEdit):
                    widget.setText(value)
                elif isinstance(widget, QTextEdit):
                    widget.setPlainText(value)
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(value)

        # Set the button to "Update" mode
        self.set_update_button_mode(is_edit_mode=True)
        self.update_fields_visibility()

    def search_tools(self):
        """Start the debounce timer for search."""
        self.search_timer.start(300)  # Wait 300ms after the last keypress

    def perform_search(self):
        """Perform the actual search operation."""
        keyword = self.search_input.text().strip()
        if keyword:
            filtered_data, _ = self.db.fetch_filtered(keyword)  # Assume fetch_filtered handles searching
            self.load_data(filtered_data)
        else:
            self.load_data()  # Load all data when the input is empty

    def get_form_data(self):
        """
        Retrieve data from all form fields in the order defined by `self.column_names`.

        Returns:
            list: A list containing the values from all input fields, aligned with `self.column_names`.
        """
        data = []
        for column in self.column_names:  # Use dynamic column names to ensure correct order
            widget = self.tool_inputs.get(column)
            if not widget:
                data.append(None)  # Handle missing widgets gracefully
                continue

            # Check if the widget is a container with a layout
            if widget.layout():
                # Retrieve the first widget in the layout (e.g., QLineEdit for custom widgets)
                inner_widget = widget.layout().itemAt(0).widget() if widget.layout().count() > 0 else None
                if isinstance(inner_widget, QLineEdit):
                    data.append(inner_widget.text().strip())  # Retrieve the text from QLineEdit
                elif isinstance(inner_widget, QTextEdit):
                    data.append(inner_widget.toPlainText().strip())  # Retrieve the text from QTextEdit
                else:
                    data.append(None)  # Unsupported or unrecognized widget
            else:
                # Handle standard widgets directly
                if isinstance(widget, QLineEdit):
                    data.append(widget.text().strip())
                elif isinstance(widget, QTextEdit):
                    data.append(widget.toPlainText().strip())
                elif isinstance(widget, QComboBox):
                    data.append(widget.currentText().strip() if widget.currentText() else None)
                else:
                    data.append(None)  # Unsupported or unrecognized widget

        return data


    def add_tool(self, from_init=False):
        """
        Prepare the form for adding a new tool.

        Clears all input fields and sets the form to "Add" mode, allowing the user
        to input details for a new tool entry.
        """
        try:
            # Clear all fields dynamically
            for field_name, widget in self.tool_inputs.items():
                if widget.layout():
                    # Handle custom widgets with layouts
                    inner_widget = widget.layout().itemAt(0).widget() if widget.layout().count() > 0 else None
                    if isinstance(inner_widget, QLineEdit):
                        inner_widget.clear()  # Clear QLineEdit
                    elif isinstance(inner_widget, QTextEdit):
                        inner_widget.clear()  # Clear QTextEdit
                else:
                    # Handle standard widgets
                    if isinstance(widget, QLineEdit):
                        widget.clear()
                    elif isinstance(widget, QTextEdit):
                        widget.clear()
                    elif isinstance(widget, QComboBox):
                        widget.setCurrentIndex(0)

            # Set default for Shape field
            if "Shape" in self.tool_inputs and isinstance(self.tool_inputs["Shape"], QComboBox):
                self.tool_inputs["Shape"].setCurrentText("endmill.fcstd")

            # Update visibility for fields based on default Shape
            self.update_fields_visibility()

            # Set the button to "Save" mode
            self.set_update_button_mode(is_edit_mode=False)

            if not from_init:
                QMessageBox.information(self, "Add Tool", "Fields cleared. You can now add a new tool.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def update_tool(self):
        """
        Update an existing tool or insert a new one if the ToolNumber doesn't exist.

        Collects form data, determines whether the operation is an update or
        an insert, and handles the database operation accordingly. Also publishes
        the tool to the wiki if applicable.
        """
        progress = None
        try:
            tool_number = self.get_field_text("ToolNumber")
            if not tool_number:
                raise ValueError("ToolNumber is required.")

            # Initialize progress dialog
            progress = QProgressDialog(self)
            progress.setWindowTitle("Processing")
            progress.setLabelText("Saving tool data...")
            progress.setCancelButton(None)  # Remove cancel button if unnecessary
            progress.setMinimumSize(300, 100)
            progress.setWindowModality(Qt.WindowModal)
            progress.setRange(0, 100)  # Indeterminate spinner
            progress.show()

            QApplication.processEvents()  # Ensure dialog updates
            time.sleep(0.05)  # Add a short delay
            progress.setValue(0)
            QApplication.processEvents()

            # Perform save and publish operations
            all_data, columns = self.db.fetch_all()
            existing_tool_numbers = [str(row[columns.index("ToolNumber")]) for row in all_data]
            data = self.get_form_data()
            operation_type = "updated" if tool_number in existing_tool_numbers else "added"

            if operation_type == "updated":
                self.db.update(tool_number, data[1:])
            else:
                self.db.insert(data)

            progress.setLabelText("Publishing tool to the wiki...")
            QApplication.processEvents()  # Ensure dialog updates
            time.sleep(0.05)  # Add a short delay
            progress.setValue(0)
            QApplication.processEvents()

            # Define a progress update callback
            def progress_update(percentage):
                progress.setValue(percentage)
                QApplication.processEvents()

            # Perform the publishing operation with progress updates
            result = wiki_main(tool_number=int(tool_number), progress_callback=progress_update)

            if result["status"] == "success":
                QMessageBox.information(self, "Success", f"Tool {tool_number} {operation_type} and published to the wiki!")
            else:
                QMessageBox.warning(self, "Partial Success", f"Tool {tool_number} {operation_type}, but failed to publish to the wiki.")

            self.set_update_button_mode(is_edit_mode=True)
            self.load_data()

        except sqlite3.Error as db_error:
            QMessageBox.critical(self, "Database Error", f"Failed to {operation_type} tool {tool_number}: {db_error}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        if progress:
            progress.close()

    def publish_all_tools(self):
        """
        Publish all tools to the wiki.

        Iterates through all tools in the database and publishes them to the wiki.
        Displays progress and handles any errors encountered during the process.
        """
        try:
            # Initialize progress dialog
            progress = QProgressDialog(self)
            progress.setWindowTitle("Processing")
            progress.setLabelText("Publishing all tools to the wiki...")
            progress.setCancelButton(None)  # Remove cancel button if unnecessary
            progress.setMinimumSize(300, 100)
            progress.setWindowModality(Qt.WindowModal)
            progress.setRange(0, 100)  # Indeterminate spinner
            progress.show()

            QApplication.processEvents()  # Ensure dialog updates
            time.sleep(0.05)  # Add a short delay
            progress.setValue(0)
            QApplication.processEvents()

            # Define a progress update callback
            def progress_update(percentage):
                progress.setValue(percentage)
                QApplication.processEvents()

            # Perform the publishing operation with progress updates
            result = wiki_main(tool_number=None, progress_callback=progress_update)

            progress.setValue(100)  # Complete progress
            QApplication.processEvents()

            if result["status"] == "success":
                QMessageBox.information(self, "Success", "All tools have been successfully published to the wiki!")
            else:
                QMessageBox.warning(self, "Partial Success", f"Some tools may have failed to publish: {result['message']}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while publishing tools: {str(e)}")
        finally:
            progress.close()

    def get_field_text(self, field_name):
        """
        Retrieve the text from a field, handling both standard and custom widgets.
        Args:
            field_name (str): The name of the field to retrieve.

        Returns:
            str: The text of the field, or None if not found.
        """
        widget = self.tool_inputs.get(field_name)
        if widget:
            if widget.layout():
                # Access the first widget in the layout (e.g., QLineEdit in custom widgets)
                inner_widget = widget.layout().itemAt(0).widget() if widget.layout().count() > 0 else None
                if isinstance(inner_widget, QLineEdit):
                    return inner_widget.text().strip()
            elif isinstance(widget, QLineEdit):
                return widget.text().strip()
            elif isinstance(widget, QTextEdit):
                return widget.toPlainText().strip()
            elif isinstance(widget, QComboBox):
                return widget.currentText().strip()
        return None

    def delete_tool(self):
        """
        Delete the selected tool, its wiki page, and its associated image file after confirmation.

        Prompts the user for confirmation before performing the deletion.
        Removes the tool from the database, attempts to delete the associated wiki page
        and image file, and always updates the tool library index.
        """
        progress = None  # Initialize progress to ensure it's always defined
        try:
            tool_number = self.get_field_text("ToolNumber")
            if not tool_number:
                raise ValueError("ToolNumber is required for deletions.")

            # Confirmation dialog
            confirm = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete Tool Number {tool_number}, its wiki page, and associated image?",
                QMessageBox.Yes | QMessageBox.No
            )

            if confirm == QMessageBox.Yes:
                # Initialize progress dialog
                progress = QProgressDialog(self)
                progress.setWindowTitle("Processing")
                progress.setLabelText("Deleting tool...")
                progress.setCancelButton(None)
                progress.setMinimumSize(300, 100)
                progress.setWindowModality(Qt.WindowModal)
                progress.setRange(0, 4)
                progress.show()
                QApplication.processEvents()
                time.sleep(0.05)  # Add a short delay
                progress.setValue(0)
                QApplication.processEvents()

                # Perform database deletion
                self.db.delete(tool_number)

                # Extract credentials and session
                api_url = 'https://wiki.knoxmakers.org/api.php'
                session = wiki_main(return_session=True)

                if not session:
                    raise ValueError("Failed to initialize wiki session.")

                # Attempt to delete the wiki page
                try:
                    page_title = f"Nibblerbot/tools/tool_{tool_number}"
                    progress.setLabelText("Deleting wiki page...")
                    progress.setValue(1)
                    QApplication.processEvents()
                    page_response = delete_wiki_item(session, api_url, page_title)
                    if "delete" not in page_response:
                        error_message = page_response.get("error", {}).get("info", "Unknown error occurred.")
                        QMessageBox.warning(self, "Partial Success", f"Tool {tool_number}'s wiki page could not be deleted: {error_message}")
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to delete the wiki page: {str(e)}")

                # Attempt to delete the associated image
                try:
                    progress.setLabelText("Deleting associated image...")
                    progress.setValue(2)
                    QApplication.processEvents()
                    image_title = self.tool_inputs["ToolImageFileName"].text() or f"Tool_{tool_number}.png"
                    image_response = delete_wiki_item(session, api_url, image_title, is_media=True)
                    if "delete" not in image_response:
                        error_message = image_response.get("error", {}).get("info", "Unknown error occurred.")
                        QMessageBox.warning(self, "Partial Success", f"Tool {tool_number}'s image could not be deleted: {error_message}")
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to delete the associated image: {str(e)}")

                # Always update the index page
                progress.setLabelText("Updating the index page...")
                progress.setValue(3)
                QApplication.processEvents()
                try:
                    index_page_content = generate_index_page_content(self.db.db_path)
                    generate_tools_json(self.db.db_path)
                    upload_wiki_page(session, api_url, "Nibblerbot/tools", index_page_content)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to update the index page: {str(e)}")

                progress.setValue(4)
                QApplication.processEvents()
                QMessageBox.information(self, "Success", f"Tool {tool_number} deletion process completed.")
                self.load_data()

        except sqlite3.Error as db_error:
            QMessageBox.critical(self, "Database Error", f"Failed to delete tool {tool_number}: {db_error}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.load_data()
        finally:
            if progress:
                progress.close()
            self.add_tool(from_init=True)

    def set_update_button_mode(self, is_edit_mode=True):
        """
        Set the text of the update button dynamically.

        Args:
            is_edit_mode (bool): If True, sets the button to "Update" mode. 
                                 If False, sets it to "Save" mode.
        """
        self.update_button.setText("Save" if not is_edit_mode else "Update")

def center_window(window):
    """
    Centers a given window on the primary screen.
    """
    screen = QApplication.primaryScreen()
    screen_geometry = screen.availableGeometry()
    window_geometry = window.frameGeometry()
    window_geometry.moveCenter(screen_geometry.center())
    window.move(window_geometry.topLeft())

class SplashScreen(QWidget):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Set up layout and background
        self.setStyleSheet("background-color: #2e2e2e;")
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Load and center the image
        image_label = QLabel(self)
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            print(f"Error: Unable to load image from {image_path}")
            image_label.setText("Image not found")
            image_label.setStyleSheet("color: white; font-size: 24px;")
            self.setGeometry(0, 0, 400, 300)  # Default size for error message
        else:
            image_label.setPixmap(pixmap)
            self.setGeometry(0, 0, pixmap.width(), pixmap.height())

        layout.addWidget(image_label)
        self.setLayout(layout)

        center_window(self)



if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("OpenBitLib")
    app.setApplicationDisplayName("OpenBitLib")
    app.setWindowIcon(QIcon("icons/OpenBitLib-Icon-64.png"))  # Ensure the path is correct
    app.setDesktopFileName("OpenBitLib.desktop")  # Match your desktop file name

    # Apply theme settings
    theme = config.get("gui_settings", {}).get("theme", "Fusion")
    QApplication.setStyle(theme)

    # Show the splash screen
    splash = SplashScreen("icons/OpenBitLib.png")  # Ensure the image path is correct
    splash.show()

    def load_main_window():
        window = ToolDatabaseGUI(config)
        window.setObjectName("OpenBitLib")
        window.setWindowTitle("OpenBitLib")

        # Ensure WM_CLASS is set explicitly
        window.setWindowFlag(Qt.Window)
        qwindow = window.windowHandle()  # Get the QWindow for this widget
        if qwindow:
            qwindow.setProperty("class", "OpenBitLib")  # Set the class name
            qwindow.setProperty("name", "openbitlib")  # Set the instance name

        center_window(window)
        window.show()

    QTimer.singleShot(750, splash.close)  # Close splash screen
    QTimer.singleShot(745, load_main_window)  # Load the main window

    app.exec()