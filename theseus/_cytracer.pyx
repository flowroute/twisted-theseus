# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

from twisted.internet import defer

from theseus._tracer import DeferredStatus, FakeFrame, Tracer

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
        if event == 'call':
            # Don't trace generators; inlineCallbacks is handled separately.
            if frame.f_code.co_flags & CO_GENERATOR:
                return None

            # Tracing functions from twisted.internet.defer adds a lot of
            # noise, so don't do that.
            if frame.f_globals.get('__name__') == 'twisted.internet.defer':
                # The only exception to the above is unwindGenerator, an
                # implementation detail of inlineCallbacks.
                if frame.f_code.co_name == 'unwindGenerator':
                    self._unwindGenerator_frames.add(frame)
                else:
                    return None

        elif event == 'return':
            if not isinstance(arg, defer.Deferred):
                return
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
            frame_obj = frame
            if frame in self._unwindGenerator_frames:
                self._unwindGenerator_frames.remove(frame)
                wrapped_func = frame.f_locals['f']
                frame_obj = FakeFrame(
                    wrapped_func.func_code,
                    None if frame.f_back is NULL else <object>frame.f_back)
            key = frame_obj, arg
            self._deferreds[key] = DeferredStatus(
                frame, arg, self._reactor.seconds())
            arg.addBoth(self._deferred_fired, key)

        return self._trace
