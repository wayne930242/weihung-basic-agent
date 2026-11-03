"""The unattended install profile: which pins, resources and skills a computer nobody sits at leaves out.

This is an install profile saved in the marker (state["profile"]). It is not the model strategy profile that was removed;
role models still come from pi/herdr-agents-models.json alone.
"""

from pathlib import Path

from .pins import UNATTENDED_DROPPED_SKILLS, UNATTENDED_DROPS

DEFAULT = "default"
UNATTENDED = "unattended"
PROFILES = (DEFAULT, UNATTENDED)


def is_unattended(profile: str | None) -> bool:
    return profile == UNATTENDED


def dropped_ids(profile: str | None) -> set[str]:
    """The package ids this profile leaves out."""
    return set(UNATTENDED_DROPS) if is_unattended(profile) else set()


def dropped_skills(profile: str | None) -> tuple[str, ...]:
    return UNATTENDED_DROPPED_SKILLS if is_unattended(profile) else ()


def instructions_template(root: Path, profile: str | None) -> Path:
    return root / ("pi/AGENTS.unattended.md.in" if is_unattended(profile) else "pi/AGENTS.md.in")
