# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

from twisted.internet import defer

from theseus._tracer import FakeFrame, Tracer

cdef extern from "code.h":
    ctypedef class types.CodeType [object PyCodeObject]:
        cdef int co_flags
        cdef object co_name

    int CO_GENERATOR

cdef extern from "frameobject.h":
    ctypedef class types.FrameType [object PyFrameObject]:
        cdef object f_globals
        cdef object f_locals
        cdef void *f_back
        cdef CodeType f_code


class CythonTracer(Tracer):
    def _trace(self, FrameType frame, event, arg):
        if self._wrapped_profiler is not None:
            self._wrapped_profiler(frame, event, arg)

        if event != 'return':
            return

        # Don't care about generators; inlineCallbacks is handled separately.
        if frame.f_code.co_flags & CO_GENERATOR:
            return

        # If it's not a deferred, we don't care either.
        if not isinstance(arg, defer.Deferred):
            return

        frame_obj = frame
        # Tracing functions from twisted.internet.defer adds a lot of noise, so
        # don't do that except for unwindGenerator.
        if frame.f_globals.get('__name__') == 'twisted.internet.defer':
            # Detect when unwindGenerator returns. unwindGenerator is part of
            # the inlineCallbacks implementation. If unwindGenerator is
            # returning, it means that the Deferred being returned is the
            # Deferred that will be returned from the wrapped function. Yank
            # the wrapped function out and fake a call stack that makes it look
            # like unwindGenerator isn't involved at all and the wrapped
            # function is being called directly. This /does/ involve Twisted
            # implementation details, but as far back as twisted 2.5.0 (when
            # inlineCallbacks was introduced), the name 'unwindGenerator' and
            # the local 'f' are the same. If this ever changes in the future,
            # I'll have to update this code.
            if frame.f_code.co_name == 'unwindGenerator':
                wrapped_func = frame.f_locals['f']
                frame_obj = FakeFrame(
                    wrapped_func.func_code,
                    None if frame.f_back is NULL else <object>frame.f_back)
            else:
                return

        key = frame_obj, arg
        self._deferreds[key] = self._reactor.seconds()
        arg.addBoth(self._deferred_fired, key)
