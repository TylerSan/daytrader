"""Research subsystem — strategy selection, bake-off, parameter studies.

Kept separate from `daytrader.journal` by design: journal enforces trading
discipline on the critical path; research produces evidence that feeds into
it via explicit `promote` handoffs.
"""
