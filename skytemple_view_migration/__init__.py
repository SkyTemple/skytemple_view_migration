import click

from skytemple_view_migration.collect_info import CollectInfo
from skytemple_view_migration.output import p_info
from skytemple_view_migration.phase_one import run_phase1
from skytemple_view_migration.phase_three import run_phase3
from skytemple_view_migration.phase_two import run_phase2


@click.command()
@click.argument("skytemple_directory")
@click.argument("collect_info_json")
@click.option("--phase1/--no-phase1", default=True)
@click.option("--phase2/--no-phase2", default=True)
@click.option("--phase3/--no-phase3", default=True)
def main(
    skytemple_directory: str,
    collect_info_json: str,
    phase1: bool,
    phase2: bool,
    phase3: bool,
):
    """
    Convert controllers into widget views. Will collect data from all controllers,
    and then generate widgets and convert glade files to ui templates.

    Phases (can be skipped):
    - 1. Collecting:
      Collects all controllers and generates their names, entry points and `item_data` types.
      Reads/Writes those to the collect_info_json JSON file.
    - 2. Generating:
      Generating widget UI files and Python widget modules.
    - 3. Cleaning:
      Delete old controllers and glade files.
    """
    collect_info = CollectInfo(collect_info_json)
    if phase1:
        run_phase1(skytemple_directory, collect_info)
        p_info("Saving collect info.")
        collect_info.dump()
    if phase2:
        run_phase2(skytemple_directory, collect_info)
    if phase3:
        run_phase3(skytemple_directory, collect_info)


if __name__ == "__main__":
    main()
