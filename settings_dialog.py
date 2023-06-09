# Copyright: Ren Tatsumoto <tatsu at autistici.org>
# Copyright (c) 2023 mizmu addons 
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from typing import Iterable

from aqt import mw
from aqt.qt import *
from aqt.utils import restoreGeom, saveGeom, disable_help_button

from .ajt_common.about_menu import tweak_window, menu_root_entry
from .common import ADDON_NAME
from .config import config, write_config
from .widgets import ItemBox, SpinBox


def fetch_toggleables() -> Iterable[str]:
    for key, value in config.items():
        if type(value) == bool:
            yield key


def make_checkboxes() -> dict[str, QCheckBox]:
    return {key: QCheckBox(key.replace('_', ' ').capitalize()) for key in fetch_toggleables()}


class CroProSettingsDialog(QDialog):
    name = 'cropro_settings_dialog'

    def __init__(self, main_form, current_col, *args, **kwargs) -> None:
        QDialog.__init__(self, *args, **kwargs)
        self.main_form = main_form
        self.current_col = current_col
        disable_help_button(self)
        self._setup_ui()
        tweak_window(self)
        restoreGeom(self, self.name, adjustSize=True)

    def _setup_ui(self) -> None:
        self.setMinimumWidth(300)
        self.setWindowTitle(f"{ADDON_NAME} Settings")
        self.setLayout(self._make_layout())
        self.connect_widgets()
        self.add_tooltips()

    def _make_layout(self) -> QLayout:
        self.hidden_fields_box = ItemBox(parent=self, initial_values=config['hidden_fields'])
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.checkboxes = make_checkboxes()

        layout = QVBoxLayout()
        layout.addLayout(self._make_form())
        layout.addWidget(self.hidden_fields_box)
        for key, checkbox in self.checkboxes.items():
            layout.addWidget(checkbox)
            checkbox.setChecked(config.get(key))
        layout.addStretch()
        layout.addWidget(self.button_box)
        return layout

    def _make_form(self) -> QFormLayout:
        self.tag_edit = QLineEdit(config['exported_tag'])
        self.max_notes_edit = SpinBox(min_val=10, max_val=10_000, step=50, value=config['max_displayed_notes'])
        self.hidden_fields_edit = QLineEdit()
        self.hidden_fields_edit.setPlaceholderText("New item")

        layout = QFormLayout()
        layout.addRow("Max displayed notes", self.max_notes_edit)
        layout.addRow("Tag original cards with", self.tag_edit)
        layout.addRow("Hide fields matching", self.hidden_fields_edit)
        return layout

    def connect_widgets(self):
        qconnect(self.button_box.accepted, self.accept)
        qconnect(self.button_box.rejected, self.reject)
        qconnect(self.hidden_fields_edit.textChanged, lambda: self.hidden_fields_box.new_item(self.hidden_fields_edit))

    def add_tooltips(self) -> None:
        self.hidden_fields_edit.setToolTip(
            "Hide fields whose names contain these words.\n"
            "Press space or comma to commit."
        )

    def finished(self, result: int) -> None:
        saveGeom(self, self.name)
        return super().finished(result)

    def accept(self) -> None:
        config['max_displayed_notes'] = self.max_notes_edit.value()
        config['exported_tag'] = self.tag_edit.text()
        config['hidden_fields'] = self.hidden_fields_box.values()
        for key, checkbox in self.checkboxes.items():
            config[key] = checkbox.isChecked()
        write_config()
        from .cropro import MainDialog
        d = MainDialog(parent=mw, current_col=self.current_col)
        d.show()
        return super().accept()

    def reject(self) -> None:
        from .cropro import MainDialog
        d = MainDialog(parent=mw, current_col=self.current_col)
        d.show()
        return super().reject()

