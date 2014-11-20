# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

try:
    from theseus._cytracer import CythonTracer as Tracer
except ImportError:
    from theseus._tracer import Tracer
from theseus._version import __version__, __sha__


__all__ = ['__version__', '__sha__', 'Tracer']
