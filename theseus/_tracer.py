import collections
import sys

from twisted.internet import defer
from twisted.python import log


DeferredStatus = collections.namedtuple(
    'DeferredStatus', ['frame', 'deferred', 'returned_at'])
FunctionData = collections.namedtuple('FunctionData', ['calls', 'time'])
FunctionCall = collections.namedtuple('FunctionCall', ['count', 'time'])
EMPTY_CALL = FunctionCall(0, 0)
IGNORE = object()


class Function(collections.namedtuple('Function', ['filename', 'func'])):
    @classmethod
    def of_frame(cls, frame):
        return cls(frame.f_code.co_filename, frame.f_code.co_name)


class Tracer(object):
    def __init__(self, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor
        self._deferreds = {}
        self._function_data = {}

    def _trace(self, frame, event, arg):
        meth = getattr(self, '_event_' + event, None)
        result = None
        if meth is not None:
            result = meth(frame, arg)
        if result is not IGNORE:
            return self._trace

    def _event_call(self, frame, arg):
        if frame.f_globals.get('__name__') == 'twisted.internet.defer':
            return IGNORE

    def _event_return(self, frame, arg):
        if not isinstance(arg, defer.Deferred):
            return
        key = frame, arg
        self._deferreds[key] = DeferredStatus(
            frame, arg, self._reactor.seconds())
        arg.addBoth(self._deferred_fired, key)

    def _get_function(self, frame):
        func = Function.of_frame(frame)
        data = self._function_data.get(func)
        if data is None:
            data = self._function_data[func] = FunctionData({}, 0)
        return func, data

    def _deferred_fired(self, result, key):
        fired_at = self._reactor.seconds()
        status = self._deferreds.pop(key, None)
        if status is None:
            return
        delta = int((fired_at - status.returned_at) * 1000000)
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
        sys.settrace(self._trace)

    def write_data(self, fobj):
        fobj.write('events: Nanoseconds\n')
        for func, data in sorted(self._function_data.iteritems()):
            fobj.write('fn={0.func} {0.filename}\n'.format(func))
            fobj.write('0 {0.time}\n'.format(data))
            for callee, call in sorted(data.calls.iteritems()):
                fobj.write('cfn={0.func} {0.filename}\n'.format(callee))
                fobj.write('calls={0.count} 0\n0 {0.time}\n'.format(call))
            fobj.write('\n')
