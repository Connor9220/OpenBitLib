#!/usr/bin/env python3
"""
Tree-based Shape Selector Widget
Displays shapes and subtypes in a hierarchical tree structure, similar to FreeCAD's interface.
"""

from qtpy.QtWidgets import (
    QComboBox,
    QTreeWidget,
    QTreeWidgetItem,
    QStyledItemDelegate,
)
from qtpy.QtCore import Qt, Signal, QModelIndex
from qtpy.QtGui import QFont


class ShapeTreeComboBox(QComboBox):
    """
    A ComboBox that displays shapes and subtypes in a tree structure.

    Usage:
        combo = ShapeTreeComboBox()
        combo.populate_shapes(shapes_with_subtypes_dict)
        shape, subtype = combo.get_selection()
        combo.set_selection("Endmill", "upcut")
    """

    # Custom signal emitted when selection changes with (shape, subtype)
    shapeSelectionChanged = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Make the combo box editable so we can set custom text
        self.setEditable(True)
        # Prevent user from manually editing the text
        self.lineEdit().setReadOnly(True)

        # Create tree widget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setRootIsDecorated(False)  # Hide expand/collapse arrows
        self.tree_widget.setAnimated(True)
        self.tree_widget.setIndentation(15)  # Set indent to 15 pixels

        # Increase dropdown popup height
        self.tree_widget.setMinimumHeight(300)  # Set minimum height to 300 pixels

        # Set the tree widget as the view for the combo box
        self.setModel(self.tree_widget.model())
        self.setView(self.tree_widget)

        # Track current selection
        self.current_shape = None
        self.current_subtype = None
        self._current_item = None  # Track the currently selected item

        # Flag to prevent signal handling during programmatic updates
        self._updating_programmatically = False

        # Connect signals
        self.tree_widget.itemClicked.connect(self._on_item_clicked)
        # Also connect to currentItemChanged for when selection changes via keyboard/other means
        self.tree_widget.currentItemChanged.connect(self._on_current_item_changed)
        # Connect to activated signal to catch selection from dropdown
        self.activated.connect(self._on_activated)

    def populate_shapes(self, shapes_with_subtypes):
        """
        Populate the tree with shapes and subtypes.

        Args:
            shapes_with_subtypes (dict): Dictionary mapping shape_type to list of subtypes
                                        {"Endmill": [{"subtype_name": "upcut", "display_name": "Upcut"}, ...], ...}
        """
        self.tree_widget.clear()
        self.shape_items = {}  # Map shape_type to QTreeWidgetItem
        self.subtype_items = {}  # Map (shape_type, subtype_name) to QTreeWidgetItem

        for shape_type in sorted(shapes_with_subtypes.keys()):
            subtypes = shapes_with_subtypes[shape_type]

            # Create parent item for shape
            shape_item = QTreeWidgetItem(self.tree_widget)
            shape_item.setText(0, shape_type)
            shape_item.setData(0, Qt.UserRole, {"type": "shape", "shape": shape_type})

            # Make parent items bold
            # font = shape_item.font(0)
            # font.setBold(True)
            # shape_item.setFont(0, font)

            self.shape_items[shape_type] = shape_item

            # Add subtypes as children
            if subtypes:
                for subtype_info in subtypes:
                    subtype_name = subtype_info["subtype_name"]
                    display_name = subtype_info["display_name"]

                    subtype_item = QTreeWidgetItem(shape_item)
                    subtype_item.setText(0, display_name)  # Use default tree indent
                    subtype_item.setData(
                        0,
                        Qt.UserRole,
                        {
                            "type": "subtype",
                            "shape": shape_type,
                            "subtype": subtype_name,
                            "display_name": display_name,
                        },
                    )

                    self.subtype_items[(shape_type, subtype_name)] = subtype_item

        # Expand all items by default
        self.tree_widget.expandAll()

    def showPopup(self):
        """Override to ensure the correct item is highlighted when the dropdown opens."""
        # Reset root to show the full tree (not restricted to a subtree)
        self.setRootModelIndex(QModelIndex())
        super().showPopup()
        # After Qt opens the popup, force our item to be highlighted
        if self._current_item:
            index = self.tree_widget.indexFromItem(self._current_item)
            self.view().setCurrentIndex(index)
            self.tree_widget.scrollToItem(self._current_item)

    def _on_item_clicked(self, item, column):
        """Handle item selection in the tree."""
        if self._updating_programmatically:
            return

        data = item.data(0, Qt.UserRole)

        if data["type"] == "shape":
            # Parent shape selected (no subtype)
            self.current_shape = data["shape"]
            self.current_subtype = None
            self._current_item = item
            self.lineEdit().setText(data["shape"])

        elif data["type"] == "subtype":
            # Subtype selected
            self.current_shape = data["shape"]
            self.current_subtype = data["subtype"]
            self._current_item = item
            display_text = f"{data['shape']} - {data['display_name']}"
            self.lineEdit().setText(display_text)

        # Emit custom signal
        self.shapeSelectionChanged.emit(self.current_shape, self.current_subtype or "")

        # Close the popup
        self.hidePopup()

    def _on_current_item_changed(self, current, previous):
        """Handle when the current item in the tree changes."""
        if self._updating_programmatically:
            return

        if not current:
            return

        data = current.data(0, Qt.UserRole)
        if not data:
            return

        if data["type"] == "shape":
            # Parent shape selected (no subtype)
            self.current_shape = data["shape"]
            self.current_subtype = None

        elif data["type"] == "subtype":
            # Subtype selected
            self.current_shape = data["shape"]
            self.current_subtype = data["subtype"]

    def _on_activated(self, index):
        """Handle when an item is activated (selected) from the combo box."""
        if self._updating_programmatically:
            return

        # Get the currently selected item in the tree
        current_item = self.tree_widget.currentItem()
        if current_item:
            data = current_item.data(0, Qt.UserRole)
            if data:
                if data["type"] == "shape":
                    self.current_shape = data["shape"]
                    self.current_subtype = None
                    self._current_item = current_item
                    self.lineEdit().setText(data["shape"])
                elif data["type"] == "subtype":
                    self.current_shape = data["shape"]
                    self.current_subtype = data["subtype"]
                    self._current_item = current_item
                    display_text = f"{data['shape']} - {data['display_name']}"
                    self.lineEdit().setText(display_text)

                # Emit custom signal
                self.shapeSelectionChanged.emit(
                    self.current_shape, self.current_subtype or ""
                )

    def get_selection(self):
        """
        Get the current selection.

        Returns:
            tuple: (shape_type, subtype_name) or (shape_type, None) if no subtype
        """
        return self.current_shape, self.current_subtype

    def set_selection(self, shape_type, subtype_name=None):
        """
        Set the current selection programmatically.

        Args:
            shape_type (str): The shape type to select
            subtype_name (str, optional): The subtype to select
        """
        if not shape_type:
            return

        # Block signal handlers during programmatic update
        self._updating_programmatically = True

        try:
            self.current_shape = shape_type
            self.current_subtype = subtype_name

            if subtype_name:
                # Find and select the subtype item
                item_key = (shape_type, subtype_name)
                if item_key in self.subtype_items:
                    item = self.subtype_items[item_key]
                    self._current_item = item
                    data = item.data(0, Qt.UserRole)
                    display_text = f"{shape_type} - {data['display_name']}"

                    # Expand parent to show the selected subtype
                    if shape_type in self.shape_items:
                        self.shape_items[shape_type].setExpanded(True)

                    # Select and highlight the item in the tree view
                    self.tree_widget.setCurrentItem(item)
                    item.setSelected(True)
                    self.tree_widget.scrollToItem(item)
                    index = self.tree_widget.indexFromItem(item)
                    self.view().setCurrentIndex(index)

                    # Set the display text in the combo box
                    self.lineEdit().setText(display_text)
                else:
                    # Subtype not found - fallback to parent only
                    print(
                        f"Warning: Subtype '{subtype_name}' not found for shape '{shape_type}'"
                    )
                    if shape_type in self.shape_items:
                        item = self.shape_items[shape_type]
                        self._current_item = item
                        self.tree_widget.setCurrentItem(item)
                        item.setSelected(True)
                        self.tree_widget.scrollToItem(item)
                        index = self.tree_widget.indexFromItem(item)
                        self.view().setCurrentIndex(index)
                        self.lineEdit().setText(shape_type)
            else:
                # Just select the shape
                if shape_type in self.shape_items:
                    item = self.shape_items[shape_type]
                    self._current_item = item
                    self.tree_widget.setCurrentItem(item)
                    item.setSelected(True)
                    self.tree_widget.scrollToItem(item)
                    index = self.tree_widget.indexFromItem(item)
                    self.view().setCurrentIndex(index)
                    self.lineEdit().setText(shape_type)
        finally:
            # Always re-enable signal handlers
            self._updating_programmatically = False

    def get_shape(self):
        """Get the selected shape type."""
        return self.current_shape

    def get_subtype(self):
        """Get the selected subtype name (or None)."""
        return self.current_subtype
