#!/usr/bin/env python3
"""Pre-commit helper: print the number of pending Barsukas string replacements."""

from strings.generate_barsukas_strings import compute_plan


def main() -> int:
    template_plans, catalog_state, _stats = compute_plan()
    pending = sum(len(items) for items in template_plans.values())
    print(pending)
    has_new_keys = any(catalog_state.new_keys.values())
    return 1 if pending > 0 or has_new_keys else 0


if __name__ == "__main__":
    raise SystemExit(main())
