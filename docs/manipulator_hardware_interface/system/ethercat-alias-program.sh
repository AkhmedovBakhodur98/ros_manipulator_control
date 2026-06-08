#!/usr/bin/env bash
#
# Burn EEPROM aliases 1..6 into the A6N drives of the full manipulator
# chain. Stage 6.6b — once-per-drive setup so URDF can stop caring about
# physical cable order (manipulator_ethercat_full.urdf.xacro uses
# alias=N, position=0 for every joint).
#
# Required physical chain BEFORE running this script:
#
#   master (eno1) -> A6-750EC (X rail)
#                 -> A6-750EC (Z lift)
#                 -> A6-750EC (Z picker / A)
#                 -> A6-750EC (SCARA shoulder)
#                 -> A6-400EC (SCARA elbow)
#                 -> A6-200EC (SCARA wrist)
#
# Mapping by ethercat position (0..5) -> burned alias (1..6):
#
#   position 0 (X rail)     -> alias 1
#   position 1 (Z lift)     -> alias 2
#   position 2 (Z picker)   -> alias 3
#   position 3 (shoulder)   -> alias 4
#   position 4 (elbow)      -> alias 5
#   position 5 (wrist)      -> alias 6
#
# After running, power-cycle the chain. `ethercat slaves` should now
# show the alias column populated for every drive; the URDF can be
# rewired in any cable order without further edits.

set -euo pipefail

if ! command -v ethercat >/dev/null; then
    echo "ethercat (IgH userspace tool) not found in PATH — load /etc/init.d/ethercat first" >&2
    exit 1
fi

echo "Current chain layout:"
ethercat slaves
echo

# Sanity: expect exactly 6 slaves before touching EEPROM. Bailing out
# here is the right behaviour — burning an alias on the wrong slave is
# a 5-minute fix with the SII tool but only if you notice the mistake.
count=$(ethercat slaves | grep -c '^' || true)
if [[ "$count" -ne 6 ]]; then
    echo "Expected 6 slaves in the chain, found ${count}. Aborting — fix the cabling first." >&2
    exit 1
fi

declare -A LABEL=(
    [0]="X rail (A6-750EC)"
    [1]="Z lift (A6-750EC)"
    [2]="Z picker (A6-750EC)"
    [3]="SCARA shoulder (A6-750EC)"
    [4]="SCARA elbow (A6-400EC)"
    [5]="SCARA wrist (A6-200EC)"
)

for pos in 0 1 2 3 4 5; do
    alias=$((pos + 1))
    echo "Position ${pos} (${LABEL[$pos]}) -> alias ${alias}"
    sudo ethercat alias -p "${pos}" "${alias}"
done

echo
echo "Done. Power-cycle the drives (or restart the EtherCAT master) so the new aliases take effect, then re-check with 'ethercat slaves'."
