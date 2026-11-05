# unittas (Python)

The Python side of unitTAS: the orchestrator, and the protocol it speaks with the probe inside the game. Being built
(phase 2 of the pivot); unitTAS's manual is the repository's README.md.

- `mamba env create -f environment.yml`, in the repository's root, makes the conda environment `unittas_env`
  (`mamba env update -f environment.yml --prune` brings it up to date).
- `python -m unittest discover -s python/tests/unit` runs the tests that need no game.
