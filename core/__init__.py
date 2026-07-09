"""Framework internals: app registry, base model, router discovery.

Importing this package installs the beartype import hook so every module
under ``apps.*``, ``core.*`` and ``config.*`` is runtime type-checked.
"""

from beartype.claw import beartype_packages

beartype_packages(("apps", "core", "config"))
