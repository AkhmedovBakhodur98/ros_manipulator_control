# Published by the safety/limit-monitor node when a drive raises one of
# its hardware overtravel signals. Stage 6.6b — addresses the JTC
# SUCCEEDED-while-self-clamped hole from Stage 6.6a (bringup.md §Stage 6.6a).
#
# The drive halts the axis on its own (verified Stage 6.6a, in-motion test
# on A6-200EC); this event exists so application/UI layers learn about it
# instead of trusting JTC's SUCCEEDED result.

builtin_interfaces/Time stamp
string  joint_name
uint16  status_word         # raw 0x6041 (bit 11 = "Internal limit active")
uint32  digital_inputs      # raw 0x60FD (bit 0 = N-OT, bit 1 = P-OT, bit 2 = HomeSwitch)
bool    p_ot_active
bool    n_ot_active
bool    internal_limit_active
