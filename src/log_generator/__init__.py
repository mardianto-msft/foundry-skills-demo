"""Sample-log generator for the foundry-skills prompt-agent demo.

Generates deterministic, self-contained sample logs (web / k8s / mixed)
each containing a single, identifiable planted root-cause signature plus a
ground-truth ``*.expected.json`` file for validation.

Standard library only. See :mod:`log_generator.generate`.
"""

__all__ = ["generate"]
__version__ = "1.0.0"
