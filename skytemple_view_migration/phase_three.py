import os

from skytemple_view_migration import CollectInfo, p_info


def run_phase3(skytemple_directory: str, collect_info: CollectInfo):
    p_info("Starting Phase 3.")
    for entry in collect_info.entries.values():
        os.unlink(entry.glade_path)
        os.unlink(entry.controller_path)
    p_info("Old files deleted.")
