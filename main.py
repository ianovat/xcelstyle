#!/usr/bin/env python3
"""XcelStyle — simple cross-platform spreadsheet app (PySide6 + SQLite)."""

import os
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ── Constants ─────────────────────────────────────────────────────────────────

ROWS = 50
COLS = 26
HEADER_BG = "#EBEBEB"
DEFAULT_FAMILY = "Arial"
DEFAULT_SIZE = 11


# ── Database path ─────────────────────────────────────────────────────────────

def get_db_path() -> Path:
    """Return a platform-appropriate writable path for the SQLite database."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    app_dir = base / "XcelStyle"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / "spreadsheets.db"


# ── Database layer ────────────────────────────────────────────────────────────

class Database:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sheets (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS cells (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_id    INTEGER NOT NULL,
                row         INTEGER NOT NULL,
                col         INTEGER NOT NULL,
                content     TEXT    NOT NULL DEFAULT '',
                bold        INTEGER NOT NULL DEFAULT 0,
                italic      INTEGER NOT NULL DEFAULT 0,
                font_size   INTEGER NOT NULL DEFAULT 11,
                font_family TEXT    NOT NULL DEFAULT 'Arial',
                bg_color    TEXT    NOT NULL DEFAULT '',
                text_color  TEXT    NOT NULL DEFAULT '',
                UNIQUE (sheet_id, row, col),
                FOREIGN KEY (sheet_id) REFERENCES sheets (id) ON DELETE CASCADE
            );
        """)
        self.conn.commit()

    # sheets ------------------------------------------------------------------

    def get_sheets(self):
        return self.conn.execute(
            "SELECT id, name FROM sheets ORDER BY name"
        ).fetchall()

    def add_sheet(self, name: str) -> int:
        cur = self.conn.execute("INSERT INTO sheets (name) VALUES (?)", (name,))
        self.conn.commit()
        return cur.lastrowid

    def rename_sheet(self, sheet_id: int, new_name: str):
        self.conn.execute(
            "UPDATE sheets SET name=? WHERE id=?", (new_name, sheet_id)
        )
        self.conn.commit()

    def delete_sheet(self, sheet_id: int):
        self.conn.execute("DELETE FROM sheets WHERE id=?", (sheet_id,))
        self.conn.commit()

    # cells -------------------------------------------------------------------

    def get_cells(self, sheet_id: int):
        return self.conn.execute(
            "SELECT row, col, content, bold, italic, font_size, font_family, "
            "bg_color, text_color FROM cells WHERE sheet_id=?",
            (sheet_id,),
        ).fetchall()

    def save_cell(
        self,
        sheet_id: int,
        row: int,
        col: int,
        content: str,
        bold: int,
        italic: int,
        font_size: int,
        font_family: str,
        bg_color: str,
        text_color: str,
    ):
        self.conn.execute(
            """
            INSERT INTO cells
                (sheet_id, row, col, content, bold, italic,
                 font_size, font_family, bg_color, text_color)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sheet_id, row, col) DO UPDATE SET
                content=excluded.content,
                bold=excluded.bold,
                italic=excluded.italic,
                font_size=excluded.font_size,
                font_family=excluded.font_family,
                bg_color=excluded.bg_color,
                text_color=excluded.text_color
            """,
            (
                sheet_id, row, col, content, bold, italic,
                font_size, font_family, bg_color, text_color,
            ),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


# ── Spreadsheet grid ──────────────────────────────────────────────────────────

class SpreadsheetGrid(QTableWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(ROWS, COLS, parent)
        self.db = db
        self.sheet_id: int | None = None
        self._loading = False

        self.setHorizontalHeaderLabels([chr(65 + i) for i in range(COLS)])
        self.setVerticalHeaderLabels([str(i + 1) for i in range(ROWS)])
        for col in range(COLS):
            self.setColumnWidth(col, 100)

        self.cellChanged.connect(self._on_cell_changed)

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_sheet(self, sheet_id: int):
        self._loading = True
        self.sheet_id = sheet_id
        self.clearContents()
        self._stamp_headers()

        for row, col, content, bold, italic, font_size, font_family, bg_color, text_color in \
                self.db.get_cells(sheet_id):
            if row >= ROWS or col >= COLS:
                continue
            item = QTableWidgetItem(content)
            font = QFont(
                font_family or DEFAULT_FAMILY,
                font_size if font_size > 0 else DEFAULT_SIZE,
            )
            font.setBold(bool(bold))
            font.setItalic(bool(italic))
            item.setFont(font)
            if bg_color:
                item.setBackground(QBrush(QColor(bg_color)))
            elif row == 0 or col == 0:
                item.setBackground(QBrush(QColor(HEADER_BG)))
            if text_color:
                item.setForeground(QBrush(QColor(text_color)))
            self.setItem(row, col, item)

        self._loading = False

    def _stamp_headers(self):
        """Pre-fill row 0 and column 0 with the header background."""
        brush = QBrush(QColor(HEADER_BG))
        for col in range(COLS):
            item = QTableWidgetItem()
            item.setBackground(brush)
            self.setItem(0, col, item)
        for row in range(1, ROWS):
            item = QTableWidgetItem()
            item.setBackground(brush)
            self.setItem(row, 0, item)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _on_cell_changed(self, row: int, col: int):
        if self._loading or self.sheet_id is None:
            return
        item = self.item(row, col)
        if item is not None:
            self._persist(row, col, item)

    def _persist(self, row: int, col: int, item: QTableWidgetItem):
        font = item.font()
        font_size = font.pointSize()
        if font_size <= 0:
            font_size = DEFAULT_SIZE

        bg_brush = item.background()
        bg_color = ""
        if bg_brush.style().value != 0:  # 0 = Qt.BrushStyle.NoBrush
            candidate = bg_brush.color().name()
            # Don't store the automatic header tint as a user-chosen color
            is_header_cell = row == 0 or col == 0
            if not (is_header_cell and candidate == HEADER_BG.lower()):
                bg_color = candidate

        fg_brush = item.foreground()
        text_color = fg_brush.color().name() if fg_brush.style().value != 0 else ""

        self.db.save_cell(
            self.sheet_id, row, col,
            item.text(),
            int(font.bold()),
            int(font.italic()),
            font_size,
            font.family() or DEFAULT_FAMILY,
            bg_color,
            text_color,
        )

    # ── Formatting API ────────────────────────────────────────────────────────

    def apply_bold(self, bold: bool):
        for item in self._get_selected():
            f = item.font()
            f.setBold(bold)
            item.setFont(f)
            self._persist(item.row(), item.column(), item)

    def apply_italic(self, italic: bool):
        for item in self._get_selected():
            f = item.font()
            f.setItalic(italic)
            item.setFont(f)
            self._persist(item.row(), item.column(), item)

    def apply_font_size(self, size: int):
        for item in self._get_selected():
            f = item.font()
            f.setPointSize(size)
            item.setFont(f)
            self._persist(item.row(), item.column(), item)

    def apply_font_family(self, family: str):
        for item in self._get_selected():
            f = item.font()
            f.setFamily(family)
            item.setFont(f)
            self._persist(item.row(), item.column(), item)

    def apply_bg_color(self, color: QColor):
        for item in self._get_selected():
            item.setBackground(QBrush(color))
            self._persist(item.row(), item.column(), item)

    def apply_text_color(self, color: QColor):
        for item in self._get_selected():
            item.setForeground(QBrush(color))
            self._persist(item.row(), item.column(), item)

    def current_formatting(self) -> dict:
        item = self.currentItem()
        if item is None:
            return {
                "bold": False, "italic": False,
                "font_size": DEFAULT_SIZE, "font_family": DEFAULT_FAMILY,
            }
        f = item.font()
        return {
            "bold": f.bold(),
            "italic": f.italic(),
            "font_size": f.pointSize() if f.pointSize() > 0 else DEFAULT_SIZE,
            "font_family": f.family() or DEFAULT_FAMILY,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_selected(self) -> list[QTableWidgetItem]:
        """Return selected items, creating blank ones where the cell is empty."""
        items = []
        for idx in self.selectedIndexes():
            row, col = idx.row(), idx.column()
            item = self.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                if row == 0 or col == 0:
                    item.setBackground(QBrush(QColor(HEADER_BG)))
                self.setItem(row, col, item)
            items.append(item)
        return items


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._syncing = False  # prevents toolbar ↔ cell feedback loops

        self.setWindowTitle("XcelStyle")
        self.resize(1100, 680)
        self._build_ui()
        self._populate_sheet_list()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        splitter.addWidget(self._make_sidebar())
        splitter.addWidget(self._make_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _make_sidebar(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(160)
        w.setMaximumWidth(240)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)

        v.addWidget(QLabel("<b>Spreadsheets</b>"))

        self.sheet_list = QListWidget()
        self.sheet_list.currentItemChanged.connect(self._on_sheet_selected)
        v.addWidget(self.sheet_list)

        for label, slot in [
            ("+ New", self._add_sheet),
            ("Rename", self._rename_sheet),
            ("Delete", self._delete_sheet),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            v.addWidget(btn)

        return w

    def _make_right_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._make_toolbar())
        self.grid = SpreadsheetGrid(self.db)
        self.grid.itemSelectionChanged.connect(self._sync_toolbar)
        v.addWidget(self.grid)
        return w

    def _make_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(42)
        bar.setStyleSheet("QWidget { background: #F5F5F5; border-bottom: 1px solid #D0D0D0; }")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(4)

        # Bold
        self.btn_bold = QPushButton("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setFixedWidth(30)
        bold_font = QFont()
        bold_font.setBold(True)
        self.btn_bold.setFont(bold_font)
        self.btn_bold.clicked.connect(lambda checked: self.grid.apply_bold(checked))
        h.addWidget(self.btn_bold)

        # Italic
        self.btn_italic = QPushButton("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setFixedWidth(30)
        italic_font = QFont()
        italic_font.setItalic(True)
        self.btn_italic.setFont(italic_font)
        self.btn_italic.clicked.connect(lambda checked: self.grid.apply_italic(checked))
        h.addWidget(self.btn_italic)

        h.addWidget(_vsep())

        # Font family
        self.combo_family = QComboBox()
        self.combo_family.setMinimumWidth(160)
        self.combo_family.addItems(QFontDatabase.families())
        idx = self.combo_family.findText(DEFAULT_FAMILY)
        if idx >= 0:
            self.combo_family.setCurrentIndex(idx)
        self.combo_family.currentTextChanged.connect(self._on_family_changed)
        h.addWidget(self.combo_family)

        # Font size
        self.combo_size = QComboBox()
        self.combo_size.setMinimumWidth(58)
        self.combo_size.setEditable(True)
        for s in [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72]:
            self.combo_size.addItem(str(s))
        self.combo_size.setCurrentText(str(DEFAULT_SIZE))
        self.combo_size.currentTextChanged.connect(self._on_size_changed)
        h.addWidget(self.combo_size)

        h.addWidget(_vsep())

        # Background color
        self.btn_bg = QPushButton("BG")
        self.btn_bg.setFixedWidth(36)
        self.btn_bg.setToolTip("Cell background color")
        self.btn_bg.clicked.connect(self._pick_bg_color)
        h.addWidget(self.btn_bg)

        # Text color
        self.btn_fg = QPushButton("A")
        self.btn_fg.setFixedWidth(28)
        self.btn_fg.setToolTip("Text color")
        self.btn_fg.clicked.connect(self._pick_text_color)
        h.addWidget(self.btn_fg)

        h.addStretch()
        return bar

    # ── Toolbar ↔ cell sync ───────────────────────────────────────────────────

    def _on_family_changed(self, family: str):
        if not self._syncing:
            self.grid.apply_font_family(family)

    def _on_size_changed(self, text: str):
        if self._syncing:
            return
        try:
            size = int(text)
            if 1 <= size <= 400:
                self.grid.apply_font_size(size)
        except ValueError:
            pass

    def _pick_bg_color(self):
        color = QColorDialog.getColor(parent=self, title="Background Color")
        if color.isValid():
            self.grid.apply_bg_color(color)

    def _pick_text_color(self):
        color = QColorDialog.getColor(parent=self, title="Text Color")
        if color.isValid():
            self.grid.apply_text_color(color)

    def _sync_toolbar(self):
        """Reflect the active cell's formatting in the toolbar widgets."""
        fmt = self.grid.current_formatting()
        self._syncing = True
        self.btn_bold.setChecked(fmt["bold"])
        self.btn_italic.setChecked(fmt["italic"])
        self.combo_size.setCurrentText(str(fmt["font_size"]))
        idx = self.combo_family.findText(fmt["font_family"])
        if idx >= 0:
            self.combo_family.setCurrentIndex(idx)
        self._syncing = False

    # ── Sheet list management ─────────────────────────────────────────────────

    def _populate_sheet_list(self):
        self.sheet_list.clear()
        sheets = self.db.get_sheets()
        if not sheets:
            sheet_id = self.db.add_sheet("Sheet1")
            sheets = [(sheet_id, "Sheet1")]
        for sheet_id, name in sheets:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, sheet_id)
            self.sheet_list.addItem(item)
        self.sheet_list.setCurrentRow(0)

    def _on_sheet_selected(self, current: QListWidgetItem, _previous):
        if current is not None:
            self.grid.load_sheet(current.data(Qt.UserRole))

    def _add_sheet(self):
        name, ok = QInputDialog.getText(self, "New Spreadsheet", "Name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            sheet_id = self.db.add_sheet(name)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "XcelStyle", f'"{name}" already exists.')
            return
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, sheet_id)
        self.sheet_list.addItem(item)
        self.sheet_list.setCurrentItem(item)

    def _rename_sheet(self):
        item = self.sheet_list.currentItem()
        if item is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename Spreadsheet", "New name:", text=item.text()
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            self.db.rename_sheet(item.data(Qt.UserRole), name)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "XcelStyle", f'"{name}" already exists.')
            return
        item.setText(name)

    def _delete_sheet(self):
        item = self.sheet_list.currentItem()
        if item is None:
            return
        if self.sheet_list.count() == 1:
            QMessageBox.warning(self, "XcelStyle", "Cannot delete the last spreadsheet.")
            return
        reply = QMessageBox.question(
            self,
            "Delete Spreadsheet",
            f'Delete "{item.text()}"? This cannot be undone.',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.db.delete_sheet(item.data(Qt.UserRole))
        row = self.sheet_list.row(item)
        self.sheet_list.takeItem(row)
        self.sheet_list.setCurrentRow(max(0, row - 1))

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _vsep() -> QLabel:
    """A thin vertical separator for the toolbar."""
    sep = QLabel("|")
    sep.setStyleSheet("color: #B0B0B0; margin: 0 2px;")
    return sep


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("XcelStyle")
    db = Database(get_db_path())
    window = MainWindow(db)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
