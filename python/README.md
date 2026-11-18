# unittas

Tests that play the real Minecraft. unitTAS starts a real Minecraft client, and a dedicated server for multiplayer
tests, with its probe inside, and runs your tests against the game in the manner of Python's `unittest`. The tests
drive the game tick by tick (commands, keys, looking around, the chat, a player agent that walks and clicks) and check
what happened (blocks, inventory, entities, chat, sounds, screenshots). Verdicts go by the game's ticks, never by how
fast the machine is.

- **Minecraft 1.7.10 with Forge,** and **26.3, 1.21.1 and 1.20.1** as Mojang ships them, with Fabric Loader, with
  NeoForge (26.3, 1.21.1) or with Forge (1.20.1).
- **The probe is bundled:** each version's probe comes in this package, and an instance spec's `probe = "bundled"`
  (the default) uses it.

## Install

```
pip install unittas            # Python 3.14 or later
pip install --pre unittas      # the latest dev or rc release
```

It runs on Linux. Each version's Java (8 for 1.7.10, 25 for 26.3, 21 for 1.21.1, 17 for 1.20.1) is found in the
usual JDK folders, or named in the spec. The game's files are downloaded from Mojang's servers, and the loaders' from
theirs, into a cache (`~/.cache/unittas`), each checked against its sha1.

## Use

An instance spec, `unittas.toml` in your mod's repository, says which game:

```toml
minecraft = "26.3"
loader = { fabric = "0.20.1" }
client = "real"
mods = ["build/libs/mymod-*.jar"]
```

Then:

```
unittas run tests.test_mymod
unittas run tests.test_sync --multiplayer
```

The manual is the repository's README: <https://github.com/AsgerJon/unitTAS>.

## Working on unittas itself

- `mamba env create -f environment.yml`, in the repository's root, makes the conda environment `unittas_env`
  (`mamba env update -f environment.yml --prune` brings it up to date).
- `python -m unittest discover -s python/tests/unit` runs the tests that need no game.
