#!/usr/bin/env bash
# unitTAS: runs Python in the conda environment unittas_env (environment.yml), with the arguments given:
#   ./unittas-python.sh -m unittas.selftest connect
#   ./unittas-python.sh -m unittest discover -s python/tests/unit
# UNITTAS_PYTHON names another interpreter instead; UNITTAS_CONDA_BASE another conda base than conda's own or
# ~/miniforge3. The environment's Python is run as itself (no activation: the package needs none).
set -u
if [ -n "${UNITTAS_PYTHON:-}" ]; then
	exec "$UNITTAS_PYTHON" "$@"
fi
for base in "${UNITTAS_CONDA_BASE:-}" "$(conda info --base 2>/dev/null)" "$HOME/miniforge3"; do
	if [ -n "$base" ] && [ -x "$base/envs/unittas_env/bin/python" ]; then
		exec "$base/envs/unittas_env/bin/python" "$@"
	fi
done
echo "unittas-python: no conda environment unittas_env; make it with: mamba env create -f environment.yml (or set UNITTAS_PYTHON)" >&2
exit 2
