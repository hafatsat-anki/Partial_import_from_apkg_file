# Copyright: Ren Tatsumoto <tatsu at autistici.org>
# Copyright (c) 2023 mizmu addons 
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import json
import os
import zipfile
from typing import Optional, NamedTuple

import unicodedata
from anki.collection import Collection
from anki.importing.anki2 import MediaMapInvalid, Anki2Importer
from anki.notes import NoteId
from anki.utils import tmpfile
from aqt import mw
from aqt.utils import showInfo


class NameId(NamedTuple):
    name: str
    id: int

    @classmethod
    def none_type(cls) -> 'NameId':
        return cls('None (create new if needed)', -1)


def sorted_decks_and_ids(col: Collection) -> list[NameId]:
    return sorted(NameId(deck.name, deck.id) for deck in col.decks.all_names_and_ids())


def get_other_profile_names() -> list[str]:
    profiles = mw.pm.profiles()
    profiles.remove(mw.pm.name)
    return profiles


class CollectionManager:
    """This class keeps other collections (profiles) open and can switch between them."""

    def __init__(self):
        self._opened_cols: dict[str, Collection] = {}
        self._current_name: Optional[str] = None

    @property
    def name(self) -> Optional[str]:
        if not self.is_opened:
            raise RuntimeError("Collection vanished or was never opened.")
        return self._current_name

    @property
    def col(self):
        return self._opened_cols[self.name]

    @property
    def media_dir(self):
        return self.col.media.dir()

    @staticmethod
    def col_name_and_id() -> NameId:
        return NameId("Whole collection", -1)

    @property
    def is_opened(self) -> bool:
        return True

    def close(self):
        if self.is_opened:
            self._opened_cols.pop(self._current_name).close()
            self._current_name = None

    def close_all(self):
        for col in self._opened_cols.values():
            col.close()
        self._current_name = None
        self._opened_cols.clear()

    def open(self, name: str) -> None:
        if name not in self._opened_cols:
            zip = z = zipfile.ZipFile(name)
            # v2 scheduler?
            try:
                z.getinfo("collection.anki21")
                suffix = ".anki21"
            except KeyError:
                suffix = ".anki2"

            col = z.read(f"collection{suffix}")
            colpath = tmpfile(suffix=".anki2")
            with open(colpath, "wb") as f:
                f.write(col)
            self._current_name = name
            self._opened_cols[self.name] = Collection(colpath)
            dir = self.col.media.dir()

            self.nameToNum = {}
            try:
                media_dict = json.loads(z.read("media").decode("utf8"))
            except Exception as exc:
                raise MediaMapInvalid() from exc
            for k, v in list(media_dict.items()):
                path = os.path.abspath(os.path.join(dir, v))
                if os.path.commonprefix([path, dir]) != dir:
                    raise Exception("Invalid file")

                self.nameToNum[unicodedata.normalize("NFC", v)] = k

            for file, c in list(self.nameToNum.items()):
                path = os.path.join(self.col.media.dir(), file)
                if not os.path.exists(path):
                    # print(path)
                    with open(path, "wb") as f:
                        f.write(z.read(c))
            self.file = colpath

        self._current_name = name

    def deck_names_and_ids(self) -> list[NameId]:
        return sorted_decks_and_ids(self.col)

    def find_notes(self, deck: NameId, filter_text: str):
        if deck == self.col_name_and_id():
            return self.col.find_notes(query=filter_text)
        else:
            return self.col.find_notes(query=f'"deck:{deck.name}" {filter_text}')

    def get_note(self, note_id: NoteId):
        return self.col.get_note(note_id)
