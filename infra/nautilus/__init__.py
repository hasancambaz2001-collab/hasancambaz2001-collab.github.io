"""Paper-only Nautilus adapter. No live. No Polymarket execution client."""

from infra.nautilus.paper_engine import NautilusPaperEngine, probe_nautilus

__all__ = ["NautilusPaperEngine", "probe_nautilus"]
