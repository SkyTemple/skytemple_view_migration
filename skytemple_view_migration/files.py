import os.path
from glob import glob
from typing import Iterable

from skytemple_view_migration.model import ControllerAndGlade
from skytemple_view_migration.output import p_debug, p_warn


def iter_controllers(skytemple_directory: str) -> Iterable[ControllerAndGlade]:
    gl = os.path.join(
        os.path.abspath(skytemple_directory), "skytemple/module/*/controller/*.py"
    )
    p_debug(f"Glob Pattern: {gl}")
    for file in glob(gl):
        parts = file.split("/")
        controller_name = parts[-1][:-3]
        if controller_name == "__init__":
            continue
        module_name = parts[-3]
        p_debug(f"Collecting controller {controller_name} in {module_name}.")
        glade_path = file[:-3] + ".glade"
        # hack for the rom/main.py -> rom/rom.glade situation.
        if module_name == "rom" and controller_name == "main":
            glade_path = "/".join(glade_path.split("/")[:-1] + ["rom.glade"])
        if not os.path.exists(glade_path):
            p_warn(
                f"No glade file found for {module_name}/{controller_name}. Skipping."
            )
            continue
        yield ControllerAndGlade(module_name, controller_name, file, glade_path)
