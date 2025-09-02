"""Initialize content generators in the GeneratorRegistry."""

from api.v1.core.registries import generator_registry
from api.v1.gen.basic_rules import BasicRulesGenerator


def init_generator_registry():
    """Register all content generators with the GeneratorRegistry."""
    generator_registry.register("basic_rules", BasicRulesGenerator())
