import dataclasses
import json
import os
from dataclasses import dataclass
from typing import Optional, Dict, List

from skytemple_view_migration.model import ControllerAndGlade


@dataclass
class CollectInfoEntry:
    module_name: str
    controller_name: str
    module_class: Optional[str] = None
    main_widget_name: Optional[str] = None
    main_widget_type: Optional[str] = None
    item_data_type: Optional[str] = None
    new_widget_name: Optional[str] = None
    extra_init_params: List[str] = dataclasses.field(default_factory=list)

    def __setattr__(self, key, value):
        """Discard setting to None or empty list, if value is not None or empty list."""
        try:
            selfv = getattr(self, key)
        except AttributeError:
            return super().__setattr__(key, value)
        if value is None and selfv is not None:
            return
        if (
            isinstance(value, list)
            and len(value) < 1
            and isinstance(selfv, list)
            and len(selfv) > 0
        ):
            return
        return super().__setattr__(key, value)


class CollectInfo:
    json_file_path: str
    entries: Dict[str, CollectInfoEntry]

    def __init__(self, json_file_path: str):
        self.json_file_path = json_file_path

        if os.path.exists(self.json_file_path):
            with open(self.json_file_path, "r") as f:
                self.entries = {
                    k: CollectInfoEntry(**v) for k, v in json.load(f).items()
                }
        else:
            self.entries = {}

    def entry_for_controller(self, controller: ControllerAndGlade) -> CollectInfoEntry:
        p = controller.controller_path
        if p not in self.entries:
            self.entries[p] = CollectInfoEntry(
                controller.module_name, controller.controller_name
            )
        return self.entries[p]

    def dump(self):
        with open(self.json_file_path, "w") as f:
            json.dump(self.entries, f, cls=EnhancedJSONEncoder, indent=2)


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)
