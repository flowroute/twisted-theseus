# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

import collections
import cProfile
import inspect
import sys

from twisted.internet import defer
from twisted.python import log


FunctionData = collections.namedtuple('FunctionData', ['calls', 'time'])
FunctionCall = collections.namedtuple('FunctionCall', ['count', 'time'])
EMPTY_CALL = FunctionCall(0, 0)


class Function(collections.namedtuple('Function', ['filename', 'func'])):
    @classmethod
    def of_frame(cls, frame):
        return cls(frame.f_code.co_filename, frame.f_code.co_name)


class FakeFrame(object):
    def __init__(self, code, back):
        self.f_code = code
        self.f_back = back


class Tracer(object):
    """
    A tracer for Deferred-returning functions.

    The general idea is that if a function returns a Deferred, said Deferred
    will have a callback attached to it for timing how long it takes before the
    Deferred fires. Then, that time is recorded along with the function and all
    of its callers.
    """

    def __init__(self, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor
        self._deferreds = {}
        self._function_data = {}
        self._wrapped_profiler = None

    def _trace(self, frame, event, arg):
        if self._wrapped_profiler is not None:
            self._wrapped_profiler(frame, event, arg)

        if event != 'return':
            return

        # Don't care about generators; inlineCallbacks is handled separately.
        if frame.f_code.co_flags & inspect.CO_GENERATOR:
            return

        # If it's not a deferred, we don't care either.
        if not isinstance(arg, defer.Deferred):
            return

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
                frame = FakeFrame(wrapped_func.func_code, frame.f_back)
            else:
                return

        key = frame, arg
        self._deferreds[key] = self._reactor.seconds()
        arg.addBoth(self._deferred_fired, key)

    def _get_function(self, frame):
        func = Function.of_frame(frame)
        data = self._function_data.get(func)
        if data is None:
            data = self._function_data[func] = FunctionData({}, 0)
        return func, data

    def _deferred_fired(self, result, key):
        fired_at = self._reactor.seconds()
        returned_at = self._deferreds.pop(key, None)
        if returned_at is None:
            return
        delta = int((fired_at - returned_at) * 1000000)
        frame, _ = key
        try:
            self._record_timing(delta, frame)
        except Exception:
            log.err(None, 'an error occurred recording timing information')
        return result

    def _record_timing(self, delta, frame):
        frame_func, frame_data = self._get_function(frame)
        self._function_data[frame_func] = frame_data._replace(
            time=frame_data.time + delta)

        while frame.f_back is not None:
            caller = frame.f_back
            frame_func = Function.of_frame(frame)
            _, caller_data = self._get_function(caller)
            call = caller_data.calls.get(frame_func, EMPTY_CALL)
            caller_data.calls[frame_func] = call._replace(
                count=call.count + 1, time=call.time + delta)
            frame = caller

    def install(self):
        """
        Install this tracer as a global `profile hook
        <https://docs.python.org/2/library/sys.html#sys.setprofile>`_.

        The old profile hook, if one is set, will continue to be called by this
        tracer.
        """
        extant_profiler = sys.getprofile()
        if isinstance(extant_profiler, cProfile.Profile):
            raise RuntimeError(
                "the pure-python Tracer is unable to compose over cProfile's "
                "profile function; you must disable cProfile before "
                "installing this Tracer.")
        self._wrapped_profiler = extant_profiler
        sys.setprofile(self._trace)

    def uninstall(self):
        """
        Deactivate this tracer.

        If another profile hook was installed after this tracer was installed,
        nothing will happen. If a different profile hook was installed prior to
        calling ``install()``, it will be restored.
        """
        if sys.getprofile() == self._trace:
            sys.setprofile(self._wrapped_profiler)

    def write_data(self, fobj):
        """
        Write profiling data in `callgrind format
        <http://valgrind.org/docs/manual/cl-format.html>`_ to an open file
        object.

        The file object will not be closed.
        """
        fobj.write('events: Nanoseconds\n')
        for func, data in sorted(self._function_data.iteritems()):
            fobj.write('fn={0.func} {0.filename}\n'.format(func))
            fobj.write('0 {0.time}\n'.format(data))
            for callee, call in sorted(data.calls.iteritems()):
                fobj.write('cfn={0.func} {0.filename}\n'.format(callee))
                fobj.write('calls={0.count} 0\n0 {0.time}\n'.format(call))
            fobj.write('\n')
