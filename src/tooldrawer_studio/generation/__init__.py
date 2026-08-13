from tooldrawer_studio.generation.models import (
    GenerationIssue,
    GenerationSettings,
    GenerationState,
    GenerationValidationResult,
    HeightMode,
    ScoopMode,
)

__all__ = [
    "GenerationBlockedError",
    "GenerationBuildError",
    "GenerationIssue",
    "GenerationResult",
    "GenerationSettings",
    "GenerationState",
    "GenerationValidationResult",
    "HeightMode",
    "ScoopMode",
    "generate_organizer",
]


def __getattr__(name: str):
    if name in {
        "GenerationBlockedError",
        "GenerationBuildError",
        "GenerationResult",
        "generate_organizer",
    }:
        from tooldrawer_studio.generation.builder import (
            GenerationBlockedError,
            GenerationBuildError,
            GenerationResult,
            generate_organizer,
        )

        return {
            "GenerationBlockedError": GenerationBlockedError,
            "GenerationBuildError": GenerationBuildError,
            "GenerationResult": GenerationResult,
            "generate_organizer": generate_organizer,
        }[name]
    raise AttributeError(name)
