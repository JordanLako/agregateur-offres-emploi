from .adzuna import AdzunaSource
from .apec import ApecSource
from .base import Source, SourceUnavailable
from .francetravail import FranceTravailSource
from .hellowork import HelloWorkSource
from .linkedin import LinkedInSource
from .wttj import WelcomeToTheJungleSource

#: Toutes les sources disponibles, dans l'ordre d'affichage.
SOURCES: dict[str, type[Source]] = {
    cls.name: cls
    for cls in (
        LinkedInSource,
        HelloWorkSource,
        WelcomeToTheJungleSource,
        FranceTravailSource,
        ApecSource,
        AdzunaSource,
    )
}

__all__ = ["SOURCES", "Source", "SourceUnavailable"]
