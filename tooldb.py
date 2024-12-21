from qtpy.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QLabel, QHBoxLayout, QMessageBox, QStackedWidget, QFormLayout, QTextEdit, QComboBox, QProgressDialog, QGridLayout
)
from qtpy.QtWidgets import QWidget, QVBoxLayout
from qtpy.QtCore import Qt
from gentoolwiki import delete_wiki_item, create_session, main as wiki_main, generate_index_page_content, upload_wiki_page, generate_tools_json
import re
import time
import sqlite3
from settings import load_config

# Load the configuration
config = load_config()

print(config)

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
                    CapDiameter, CapHeight
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
                    BladeThickness, CapDiameter, CapHeight
                FROM tools
                WHERE ToolName LIKE ? OR ToolType LIKE ?
            """, (f"%{keyword}%", f"%{keyword}%"))

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
                    ShaftDiameter, SpindleDirection, SpindlePower, BladeThickness, CapDiameter, CapHeight
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    SpindleDirection = ?, SpindlePower = ?, BladeThickness = ?, CapDiameter = ?, CapHeight = ?
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
            "endmill.fcstd": ["Chipload", "CuttingEdgeHeight", "SpindleDirection"],
            "ballend.fcstd": ["Chipload", "CuttingEdgeHeight"],
            "vbit.fcstd": ["CuttingEdgeAngle", "TipDiameter", "CuttingEdgeHeight"],
            "torus.fcstd": ["TorusRadius", "CuttingEdgeHeight", "Chipload", "SpindleDirection"],
            "drill.fcstd": ["TipAngle", "Chipload"],
            "slittingsaw.fcstd": ["BladeThickness", "CapDiameter", "CapHeight"],
            "probe.fcstd": ["ShaftDiameter", "SpindlePower"],
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
            "CapHeight": "Cap Height"
        }

        # Define column names
        self.column_names = [
            "ToolNumber", "ToolName", "ToolType", "Shape", "ToolShankSize", "Flutes", "OAL",
            "LOC", "ToolMaxRPM", "ToolDiameter", "ToolMaterial", "ToolCoating", "PartNumber",
            "ManufacturerName", "ToolOrderURL", "Materials", "SuggestedRPM", "SuggestedMaxDOC",
            "AdditionalNotes", "SuggestedFeedRate", "ToolImageFileName", "Chipload", "TipAngle",
            "CuttingEdgeAngle", "TipDiameter", "TorusRadius", "ShaftDiameter", "SpindleDirection",
            "SpindlePower", "BladeThickness", "CapDiameter", "CapHeight"
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
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_tools)
        self.search_layout.addWidget(self.search_input)
        self.search_layout.addWidget(self.search_button)
        self.layout.addLayout(self.search_layout)

        # Table
        self.table = QTableWidget()
        self.table.setMinimumHeight(self.table.verticalHeader().defaultSectionSize() * 7)
        self.table.itemClicked.connect(self.load_tool_into_form)
        self.table.setSortingEnabled(True)
        self.layout.addWidget(self.table)

        # Stacked Widget for Pages
        self.stacked_widget = QStackedWidget()
        self.layout.addWidget(self.stacked_widget)

        # Define fields from the original table
        self.page1_fields = {
            "ToolNumber": {"label": self.COLUMN_LABELS["ToolNumber"], "widget": QLineEdit(), "column": "left", "width": 100},
            "ToolName": {"label": self.COLUMN_LABELS["ToolName"], "widget": QLineEdit(), "column": "left", "width": 300},
            "ToolType": {"label": self.COLUMN_LABELS["ToolType"], "widget": QLineEdit(), "column": "left", "width": 300},
            "Shape": {"label": self.COLUMN_LABELS["Shape"], "widget": QComboBox(), "column": "left", "width": 200},
            "ToolShankSize": {"label": self.COLUMN_LABELS["ToolShankSize"], "widget": QLineEdit(), "column": "left", "width": 150},
            "Flutes": {"label": self.COLUMN_LABELS["Flutes"], "widget": QLineEdit(), "column": "left", "width": 100},
            "OAL": {"label": self.COLUMN_LABELS["OAL"], "widget": QLineEdit(), "column": "left", "width": 150},
            "LOC": {"label": self.COLUMN_LABELS["LOC"], "widget": QLineEdit(), "column": "left", "width": 150},
            "ToolMaxRPM": {"label": self.COLUMN_LABELS["ToolMaxRPM"], "widget": QLineEdit(), "column": "left", "width": 150},
            "SuggestedMaxDOC": {"label": self.COLUMN_LABELS["SuggestedMaxDOC"], "widget": QLineEdit(), "column": "right", "width": 150},
            "ToolDiameter": {"label": self.COLUMN_LABELS["ToolDiameter"], "widget": QLineEdit(), "column": "left", "width": 150},
            "ToolMaterial": {"label": self.COLUMN_LABELS["ToolMaterial"], "widget": QComboBox(), "column": "left", "width": 150},
            "ToolCoating": {"label": self.COLUMN_LABELS["ToolCoating"], "widget": QLineEdit(), "column": "left", "width": 150},
            "SuggestedRPM": {"label": self.COLUMN_LABELS["SuggestedRPM"], "widget": QLineEdit(), "column": "right", "width": 300},
            "PartNumber": {"label": self.COLUMN_LABELS["PartNumber"], "widget": QLineEdit(), "column": "right", "width": 300},
            "ManufacturerName": {"label": self.COLUMN_LABELS["ManufacturerName"], "widget": QLineEdit(), "column": "right", "width": 500},
            "ToolOrderURL": {"label": self.COLUMN_LABELS["ToolOrderURL"], "widget": QLineEdit(), "column": "right", "width": 500},
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
                input_field.editingFinished.connect(
                    lambda name=field: self.format_field(name)
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

        shapes = self.db.fetch_shapes()
        if "Shape" in self.tool_inputs and isinstance(self.tool_inputs["Shape"], QComboBox):
            self.tool_inputs["Shape"].clear()  # Clear existing items
            self.tool_inputs["Shape"].addItems(shapes)
            self.tool_inputs["Shape"].currentTextChanged.connect(self.update_fields_visibility)

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
            "ToolImageFileName": {"label": self.COLUMN_LABELS["ToolImageFileName"], "widget": QLineEdit(), "width": 200},
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
            "CapHeight": {"label": self.COLUMN_LABELS["CapHeight"], "widget": QLineEdit(), "width": 150}
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

        self.stacked_widget.addWidget(self.page2)

        # Navigation Buttons
        self.nav_layout = QHBoxLayout()
        self.page1_button = QPushButton("Basic Info")
        self.page1_button.clicked.connect(lambda: self.stacked_widget.setCurrentWidget(self.page1))
        self.page2_button = QPushButton("Advanced Info")
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


    # def load_tool_into_form(self, item):
    #     """
    #     Populate the form fields with the selected row data from the table.

    #     Args:
    #         item (QTableWidgetItem): The selected item from the table widget.
    #         Used to determine the corresponding row data.
    #     """
    #     row = item.row()
    #     for col_idx, field in enumerate(self.tool_inputs.keys()):
    #         widget = self.tool_inputs[field]
    #         value = self.table.item(row, col_idx).text() if self.table.item(row, col_idx) else ""
    #         if isinstance(widget, QLineEdit) or isinstance(widget, QTextEdit):
    #             widget.setText(value)
    #         elif isinstance(widget, QComboBox):
    #             widget.setCurrentText(value)

    #     # Set the button to "Update" mode
    #     self.set_update_button_mode(is_edit_mode=True)
    #     self.update_fields_visibility()

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
            if isinstance(widget, QLineEdit) or isinstance(widget, QTextEdit):
                widget.setText(value)
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(value)

        # Set the button to "Update" mode
        self.set_update_button_mode(is_edit_mode=True)
        self.update_fields_visibility()

    def search_tools(self):
        """
        Search tools based on the keyword entered in the search bar.
        """
        keyword = self.search_input.text()
        if keyword:
            filtered_data, _ = self.db.fetch_filtered(keyword)  # Ignore columns, as load_data handles it
            self.load_data(filtered_data)
        else:
            self.load_data()

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

            # Retrieve data based on widget type
            if isinstance(widget, QLineEdit) or isinstance(widget, QTextEdit):
                text = widget.text() if isinstance(widget, QLineEdit) else widget.toPlainText()
                data.append(text if text else None)
            elif isinstance(widget, QComboBox):
                data.append(widget.currentText() if widget.currentText() else None)
        return data

    def add_tool(self, from_init=False):
        """
        Prepare the form for adding a new tool.

        Clears all input fields and sets the form to "Add" mode, allowing the user
        to input details for a new tool entry.
        """
        try:
            # Clear all fields
            for widget in self.tool_inputs.values():
                if isinstance(widget, QLineEdit) or isinstance(widget, QTextEdit):
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
        try:
            tool_number = self.tool_inputs["ToolNumber"].text()
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
        finally:
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

    def delete_tool(self):
        """
        Delete the selected tool, its wiki page, and its associated image file after confirmation.

        Prompts the user for confirmation before performing the deletion.
        Removes the tool from the database, deletes the associated wiki page
        and image file, and updates the tool library index.
        """
        try:
            tool_number = self.tool_inputs["ToolNumber"].text()
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
                progress.setRange(0, 4)  # Indeterminate spinner
                progress.show()
                QApplication.processEvents()
                time.sleep(0.05)  # Add a short delay
                progress.setValue(0)
                QApplication.processEvents()

                # Perform database deletion
                self.db.delete(tool_number)

                # Extract credentials and session
                api_url = 'https://wiki.knoxmakers.org/api.php'
                session = wiki_main(return_session=True)  # Modify `main` to return a session if requested

                if not session:
                    raise ValueError("Failed to initialize wiki session.")

                # Delete the wiki page
                page_title = f"Nibblerbot/tools/tool_{tool_number}"
                progress.setLabelText("Deleting wiki page...")
                progress.setValue(1)
                QApplication.processEvents()
                page_response = delete_wiki_item(session, api_url, page_title)

                # Log the response for debugging
                #print(f"Delete response for page '{page_title}': {page_response}")

                # Check for wiki page deletion success
                if "delete" not in page_response:
                    error_message = page_response.get("error", {}).get("info", "Unknown error occurred.")
                    QMessageBox.warning(self, "Partial Success", f"Tool {tool_number} was deleted, but the wiki page could not be deleted: {error_message}")

                # Delete the associated image
                progress.setLabelText("Deleting associated image...")
                progress.setValue(2)
                QApplication.processEvents()

                # Determine the image file name
                image_title = self.tool_inputs["ToolImageFileName"].text() or f"Tool_{tool_number}.png"
                image_response = delete_wiki_item(session, api_url, image_title, is_media=True)

                # Update the index page
                progress.setLabelText("Updating the index page...")
                progress.setValue(3)
                QApplication.processEvents()

                index_page_content = generate_index_page_content(self.db.db_path)
                generate_tools_json(self.db.db_path)
                index_update_response = upload_wiki_page(session, api_url, "Nibblerbot/tools", index_page_content)
                print(f"Index update response: {index_update_response}")

                progress.setValue(4)
                QApplication.processEvents()

                # Check for image deletion success
                if "delete" not in image_response:
                    error_message = image_response.get("error", {}).get("info", "Unknown error occurred.")
                    QMessageBox.warning(self, "Partial Success", f"Tool {tool_number}'s image could not be deleted: {error_message}")

                # Success message
                if "delete" in page_response and "delete" in image_response:
                    QMessageBox.information(self, "Success", f"Tool {tool_number}, its wiki page, and its image were successfully deleted!")

                # Refresh the data in the table
                self.load_data()

        except sqlite3.Error as db_error:
            QMessageBox.critical(self, "Database Error", f"Failed to delete tool {tool_number}: {db_error}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.load_data()
        finally:
            progress.close()


    def set_update_button_mode(self, is_edit_mode=True):
        """
        Set the text of the update button dynamically.

        Args:
            is_edit_mode (bool): If True, sets the button to "Update" mode. 
                                 If False, sets it to "Save" mode.
        """
        self.update_button.setText("Save" if not is_edit_mode else "Update")

if __name__ == "__main__":
    app = QApplication([])
    theme = config.get("gui_settings", {}).get("theme", "Fusion")
    QApplication.setStyle(theme)
    window = ToolDatabaseGUI(config)
    window.show()
    app.exec()