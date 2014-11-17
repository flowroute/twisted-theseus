from cStringIO import StringIO
import textwrap

from twisted.internet import defer, task

from theseus._tracer import Function, Tracer


class FakeFrame(object):
    def __init__(self, code=None, back=None, globals={}):
        self.f_code = code
        self.f_back = back
        self.f_globals = globals


class FakeCode(object):
    def __init__(self, filename, name):
        self.co_filename = filename
        self.co_name = name


def test_function_of_frame():
    """
    Function.of_frame examines a frame's code for its filename and code name.
    """
    frame = FakeFrame(FakeCode('spam', 'eggs'))
    assert Function.of_frame(frame) == ('spam', 'eggs')


def test_trace_normally():
    """
    Normally, a Tracer will return a local trace function for function call.
    """
    t = Tracer()
    assert t._trace(FakeFrame(), 'call', None) == t._trace


def test_trace_unknown_events():
    """
    Tracers will return a local trace function for unknown event types.
    """
    t = Tracer()
    assert t._trace(FakeFrame(), 'unknown', None) == t._trace


def test_ignore_defer():
    """
    A Tracer won't step into a function defined in twisted.internet.defer.
    """
    frame = FakeFrame(globals={'__name__': 'twisted.internet.defer'})
    t = Tracer()
    assert t._trace(frame, 'call', None) is None


def test_do_not_trace_non_deferred_returns():
    """
    If a function returns a non-Deferred value, nothing happens. More
    specifically, no function trace information is stored.
    """
    t = Tracer()
    t._trace(FakeFrame(), 'return', None)
    assert not t._function_data


_frame_spam = FakeFrame(FakeCode('spam.py', 'spam'))
_frame_eggs = FakeFrame(FakeCode('eggs.py', 'eggs'), _frame_spam)


def test_trace_deferred_return_initial_setup():
    """
    If a function returns a Deferred, nothing happens until the Deferred
    fires. More specifically, no function trace information is stored.
    """
    t = Tracer()
    d = defer.Deferred()
    t._trace(_frame_spam, 'return', d)
    assert not t._function_data


def _trace_deferred_firing_after(clock, tracer, frame, seconds):
    """
    Helper function to advance a clock and fire a Deferred.
    """
    d = defer.Deferred()
    tracer._trace(frame, 'return', d)
    clock.advance(seconds)
    d.callback(None)


def test_trace_deferred_return():
    """
    If a function returns a Deferred, after that Deferred fires, function trace
    information is stored regarding the amount of time it took for that
    Deferred to fire.
    """
    clock = task.Clock()
    t = Tracer(reactor=clock)
    _trace_deferred_firing_after(clock, t, _frame_spam, 1.5)
    assert t._function_data == {
        ('spam.py', 'spam'): ({}, 1500000),
    }


def test_trace_deferred_return_with_caller():
    """
    If the function returning the Deferred has a frame above it, that
    information is stored as well.
    """
    clock = task.Clock()
    t = Tracer(reactor=clock)
    _trace_deferred_firing_after(clock, t, _frame_eggs, 1.5)
    assert t._function_data == {
        ('spam.py', 'spam'): ({
            ('eggs.py', 'eggs'): (1, 1500000),
        }, 0),
        ('eggs.py', 'eggs'): ({}, 1500000),
    }


def test_trace_deferred_return_with_multiple_calls():
    """
    If the function(s) returning the Deferred(s) are called multiple times, the
    timing data is summed.
    """
    clock = task.Clock()
    t = Tracer(reactor=clock)
    _trace_deferred_firing_after(clock, t, _frame_spam, 0.5)
    _trace_deferred_firing_after(clock, t, _frame_spam, 0.25)
    _trace_deferred_firing_after(clock, t, _frame_eggs, 0.125)
    assert t._function_data == {
        ('spam.py', 'spam'): ({
            ('eggs.py', 'eggs'): (1, 125000),
        }, 750000),
        ('eggs.py', 'eggs'): ({}, 125000),
    }


def test_tracer_calltree_output():
    """
    Tracer's write_data method writes out calltree-formatted information.
    """
    clock = task.Clock()
    t = Tracer(reactor=clock)
    _trace_deferred_firing_after(clock, t, _frame_spam, 0.5)
    _trace_deferred_firing_after(clock, t, _frame_spam, 0.25)
    _trace_deferred_firing_after(clock, t, _frame_eggs, 0.125)
    sio = StringIO()
    t.write_data(sio)
    assert sio.getvalue() == textwrap.dedent("""\
        events: Nanoseconds
        fn=eggs eggs.py
        0 125000

        fn=spam spam.py
        0 750000
        cfn=eggs eggs.py
        calls=1 0
        0 125000

    """)


class FakeSys(object):
    tracer = None

    def settrace(self, trace):
        self.tracer = trace


def test_tracer_install(monkeypatch):
    """
    Tracer's install method will install itself globally using sys.settrace.
    """
    fakesys = FakeSys()
    t = Tracer()
    monkeypatch.setattr('theseus._tracer.sys', fakesys)
    t.install()
    assert fakesys.tracer == t._trace
