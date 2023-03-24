"""
Anki Add-on: Partial import from apkg file

GNU AGPL
Copyright (c) 2023 mizmu addons
Copyright (c) 2021 Ren Tatsumoto
Copyright (c) 2018 Russel Simmons
Original concept by CalculusAce, with help from Matt VS Japan (@mattvsjapan)

TODO:
- Handle case where user has only one profile
- Review duplicate checking: check by first field, or all fields?
- When matching model is found, verify field count (or entire map?)
"""

import json
import os.path
from collections import defaultdict

from aqt import mw, gui_hooks
from aqt.operations.deck import add_deck_dialog
from aqt.qt import *
from aqt.utils import showInfo, disable_help_button, restoreGeom, saveGeom, getFile

# from .ajt_common.about_menu import menu_root_entry
from .collection_manager import CollectionManager, sorted_decks_and_ids, NameId
from .common import ADDON_NAME, LogDebug
from .config import config
from .note_importer import import_note, ImportResult
from .settings_dialog import CroProSettingsDialog
from .widgets import SearchResultLabel, DeckCombo, ComboBox, ProfileNameLabel, StatusBar, NoteList, WIDGET_HEIGHT

logDebug = LogDebug()

# class search_edit(QLineEdit):
#     def __init__(self):
#         super().__init__()
#         self.main_dialog = None
#     def keyPressEvent(self, evt):
#         if evt.key() == QtCore.Qt.Key.Key_Enter or  evt.key() == QtCore.Qt.Key.Key_Return:
#             self.main_dialog.update_notes_list()
#         else:
#             super().keyPressEvent(evt)

#############################################################################
# UI layout
#############################################################################


class MainDialogUI(QDialog):
    name = "cropro_dialog"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.status_bar = StatusBar()
        self.search_result_label = SearchResultLabel()
        self.into_profile_label = ProfileNameLabel()
        self.current_profile_deck_combo = DeckCombo()
        self.import_button = QPushButton('Import')
        self.settings_button = QPushButton('settings')
        self.new_deck_button = QPushButton('new deck')
        self.search_term_edit = QLineEdit()
        self.search_term_edit.main_dialog = self
        self.get_apkg_button = QPushButton('choose file...')
        # self.other_profile_names_combo = ComboBox()
        self.other_profile_deck_combo = DeckCombo()
        self.filter_button = QPushButton('Filter')
        self.filter_button.setFocus()
        self.note_list = NoteList()
        self.note_type_selection_combo = ComboBox()
        self.init_ui()

    def init_ui(self):
        self.search_term_edit.setPlaceholderText('<text to filter by>')
        self.setLayout(self.make_main_layout())
        self.setWindowTitle(ADDON_NAME)
        self.set_default_sizes()

    def make_filter_row(self) -> QLayout:
        filter_row = QHBoxLayout()
        filter_row.addWidget(self.search_term_edit)
        filter_row.addWidget(self.filter_button)
        return filter_row

    def make_main_layout(self) -> QLayout:
        main_vbox = QVBoxLayout()
        main_vbox.addLayout(self.make_other_profile_settings_box())
        main_vbox.addLayout(self.make_filter_row())
        main_vbox.addWidget(self.search_result_label)
        main_vbox.addWidget(self.note_list)
        main_vbox.addLayout(self.status_bar)
        main_vbox.addLayout(self.make_input_row())
        return main_vbox

    def make_other_profile_settings_box(self) -> QLayout:
        other_profile_deck_row = QHBoxLayout()
        other_profile_deck_row.addWidget(QLabel('Import From file:'))
        other_profile_deck_row.addWidget(self.get_apkg_button)
        other_profile_deck_row.addWidget(QLabel('Deck:'))
        other_profile_deck_row.addWidget(self.other_profile_deck_combo)
        return other_profile_deck_row

    def set_default_sizes(self):
        combo_min_width = 120
        self.setMinimumSize(640, 480)
        for w in (
                self.import_button,
                self.new_deck_button,
                self.settings_button,
                self.filter_button,
                self.search_term_edit,
        ):
            w.setMinimumHeight(WIDGET_HEIGHT)
        for combo in (
                self.other_profile_deck_combo,
                self.current_profile_deck_combo,
                self.note_type_selection_combo,
        ):
            combo.setMinimumWidth(combo_min_width)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def make_input_row(self) -> QLayout:
        import_row = QHBoxLayout()
        import_row.addWidget(QLabel('Deck:'))
        import_row.addWidget(self.current_profile_deck_combo)
        import_row.addWidget(self.new_deck_button)
        import_row.addWidget(QLabel('Map to Note Type:'))
        import_row.addWidget(self.note_type_selection_combo)
        import_row.addStretch(1)
        import_row.addWidget(self.settings_button)
        import_row.addWidget(self.import_button)
        return import_row


#############################################################################
# UI logic
#############################################################################


class WindowState:
    def __init__(self, window: MainDialogUI):
        self._window = window
        self._json_filepath = os.path.join(os.path.dirname(__file__), 'user_files', 'window_state.json')
        self._map = {
            "from_deck": self._window.other_profile_deck_combo,
            "to_deck": self._window.current_profile_deck_combo,
            "note_type": self._window.note_type_selection_combo,
        }
        self._state = defaultdict(dict)

    def save(self):
        for key, widget in self._map.items():
            self._state[mw.pm.name][key] = widget.currentText()
        with open(self._json_filepath, 'w', encoding='utf8') as of:
            json.dump(self._state, of, indent=4, ensure_ascii=False)
        saveGeom(self._window, self._window.name)
        logDebug(f'saved window state.')

    def _load(self) -> bool:
        if self._state:
            return True
        elif os.path.isfile(self._json_filepath):
            with open(self._json_filepath, encoding='utf8') as f:
                self._state.update(json.load(f))
            return True
        else:
            return False

    def restore(self):
        if self._load() and (profile_settings := self._state.get(mw.pm.name)):
            for key, widget in self._map.items():
                if (value := profile_settings[key]) in widget.all_items():
                    widget.setCurrentText(value)
        restoreGeom(self._window, self._window.name, adjustSize=True)


class MainDialog(MainDialogUI):
    def __init__(self, current_col="", col_list=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_col:str = current_col
        self.col_list = col_list
        self.col_dict = {}
        self.window_state = WindowState(self)
        self.other_col = CollectionManager()
        self.connect_elements()
        disable_help_button(self)

    def connect_elements(self):
        qconnect(self.get_apkg_button.clicked, self.get_apkg)
        qconnect(self.settings_button.clicked, self.on_open_settings)
        qconnect(self.import_button.clicked, self.do_import)
        qconnect(self.filter_button.clicked, self.update_notes_list)
        qconnect(self.new_deck_button.clicked, self.on_new_deck)
        qconnect(self.search_term_edit.editingFinished, self.update_notes_list)
        qconnect(self.other_profile_deck_combo.currentIndexChanged, self.update_notes_list)

    def show(self):
        super().show()
        if self.current_col == "" and self.col_list is None:
            self.get_apkg()
        elif self.col_list is not None:
            self.get_apkg_button.setEnabled(False)
            self.other_profile_deck_combo.setEnabled(False)
            self.settings_button.setEnabled(False)
            self.update_notes_list()
        else:
            self.get_apkg_button.setText(self.current_col.split("\\")[-1])
            self.other_col.open(self.current_col)
            self.populate_other_profile_decks()
        self.populate_ui()
        self.search_term_edit.setFocus()

    def populate_ui(self):
        self.status_bar.hide()
        self.populate_note_type_selection_combo()
        self.populate_current_profile_decks()
        # 1) If the combo box is emtpy the window is opened for the first time.
        # 2) If it happens to contain the current profile name, the user has switched profiles.
        # if self.other_profile_names_combo.count() == 0 or self.other_profile_names_combo.findText(mw.pm.name) != -1:
        #     self.populate_other_profile_names()
        # self.open_other_col()
        self.into_profile_label.setText(mw.pm.name or 'Unknown')
        self.window_state.restore()

    def populate_note_type_selection_combo(self):
        self.note_type_selection_combo.clear()
        self.note_type_selection_combo.addItem(*NameId.none_type())
        for note_type in mw.col.models.all_names_and_ids():
            self.note_type_selection_combo.addItem(note_type.name, note_type.id)

    def on_new_deck(self):
        if op := add_deck_dialog(parent=self):
            op.success(lambda _: self.populate_current_profile_decks()).run_in_background()

    def get_apkg(self):
        col_name = getFile(parent=mw,
                           title="get apkg",
                           cb=None,
                           filter="*.apkg *.colpkg"
                           )
        if isinstance(col_name, str):
            self.current_col = col_name.replace("/", "\\")
            self.open_apkg()
        #else:
        #    self.get_apkg()


    def open_apkg(self):
        col_name = self.current_col
        if not self.other_col.is_opened or col_name != self.other_col.name:
            self.get_apkg_button.setText(col_name.split("\\")[-1])
            self.other_col.open(col_name)
            self.populate_other_profile_decks()

    def populate_current_profile_decks(self):
        logDebug("populating current profile decks...")
        self.current_profile_deck_combo.set_decks(sorted_decks_and_ids(mw.col))

    def populate_other_profile_decks(self):
        logDebug("populating other profile decks...")
        self.other_profile_deck_combo.set_decks([
            self.other_col.col_name_and_id(), *self.other_col.deck_names_and_ids(),
        ])

    def update_notes_list(self):
        self.search_term_edit.setFocus()
        self.search_result_label.hide()

        if self.col_list is None:
            self.open_apkg()

            if not self.search_term_edit.text() and not config['allow_empty_search']:
                return

            if self.other_profile_deck_combo.count() < 1:
                return
            try:
                note_ids = self.other_col.find_notes(self.other_profile_deck_combo.current_deck(), self.search_term_edit.text())
                limited_note_ids = note_ids[:config['max_displayed_notes']]

                self.note_list.set_notes(
                    map(self.other_col.get_note, limited_note_ids),
                    hide_fields=config['hidden_fields'],
                    media_dir=self.other_col.media_dir,
                    previewer=config['preview_on_right_side'],
                )
            except Exception as e:
                showInfo(f"error: {e}")
                return
        else:
            try:
                limited_note_ids=[]
                self.note_list.clear()
                for col_path in self.col_list:
                    col_file = col_path.replace("/", "\\")
                    cm = CollectionManager()
                    cm.open(col_file)
                    self.col_dict[col_file] = cm
                    note_ids = cm.find_notes(cm.col_name_and_id(), self.search_term_edit.text())
                    limited_note_ids += note_ids
                    self.note_list.add_notes(
                        map(cm.get_note, note_ids),
                        hide_fields=config['hidden_fields'],
                        media_dir=cm.media_dir,
                        previewer=config['preview_on_right_side'],
                    )
            except Exception as e:
                showInfo(f"error: {e}")
                return
        self.search_result_label.set_count(len(limited_note_ids), len(limited_note_ids))

    def do_import(self):
        logDebug('beginning import')

        # get selected notes
        notes = self.note_list.selected_notes()

        # clear the selection
        self.note_list.clear_selection()

        logDebug(f'importing {len(notes)} notes')

        results = []

        for note in notes:
            results.append(import_note(
                other_note=note,
                model_id=self.note_type_selection_combo.currentData(),
                deck_id=self.current_profile_deck_combo.currentData(),
            ))

        self.status_bar.set_status(results.count(ImportResult.success), results.count(ImportResult.dupe))
        mw.reset()

    def on_open_settings(self):
        self.close()
        dialog = CroProSettingsDialog(main_form=self, current_col=self.current_col, parent=mw)
        dialog.exec()

    def done(self, result_code):
        self.window_state.save()
        self.other_col.close_all()
        return super().done(result_code)


######################################################################
# Entry point
######################################################################

def init():
    # init dialog
    mw._cropro_main_dialog = MainDialog
    d = MainDialog(parent=mw)
    # get AJT menu
    root_menu = mw.form.menuTools
    # create a new menu item
    action = QAction(ADDON_NAME, root_menu)
    # set it to call show function when it's clicked
    qconnect(action.triggered, d.show)
    # and add it to the tools menu
    root_menu.addAction(action)
    # hook to close
    gui_hooks.profile_will_close.append(d.close)
