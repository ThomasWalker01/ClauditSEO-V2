# Load-bearing. Without it `tests` is not a package, so `from tests.conftest
# import FixtureSite` (18 files) resolves only when the repo root happens to be
# on sys.path. That made `python -m pytest` pass and bare `pytest` fail
# collection. CI runs bare pytest — this was CI run #1, all three jobs.
