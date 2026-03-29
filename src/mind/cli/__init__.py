"""MIND CLI package.

Re-exports ``comma_separated_ints`` so the existing import in
``app/backend/detection.py`` (``from mind.cli import comma_separated_ints``)
continues to work without modification.
"""

from typing import List


def comma_separated_ints(value: str) -> List[int]:
    """Parse a comma-separated string of integers.

    Parameters
    ----------
    value : str
        e.g. ``"1,2,3"`` or ``"7"``

    Returns
    -------
    List[int]
        Parsed integer list.

    Raises
    ------
    ValueError
        If any token is not a valid integer.
    """
    try:
        return [int(v.strip()) for v in value.split(",") if v.strip() != ""]
    except ValueError:
        raise ValueError("Topics must be comma-separated integers.")
