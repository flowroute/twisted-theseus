from cStringIO import StringIO
import inspect
import textwrap

import pytest
from twisted.internet import defer, task

from theseus._tracer import Function, Tracer


class FakeCode(object):
    def __init__(self, filename='', name='', flags=0):
        self.co_filename = filename
        self.co_name = name
        self.co_flags = flags


class FakeFrame(object):
    def __init__(self, code=FakeCode(), back=None, globals={}, locals={}):
        self.f_code = code
        self.f_back = back
        self.f_globals = globals
        self.f_locals = locals


class FakeFunction(object):
    def __init__(self, code=FakeCode()):
        self.func_code = code


def test_function_of_frame():
    """
    Function.of_frame examines a frame's code for its filename and code name.
    """
    frame = FakeFrame(FakeCode('spam', 'eggs'))
    assert Function.of_frame(frame) == ('spam', 'eggs')


def test_do_not_trace_non_deferred_returns():
    """
    If a function returns a non-Deferred value, nothing happens. More
    specifically, no function trace information is stored.
    """
    t = Tracer()
    t._trace(FakeFrame(), 'return', None)
    assert not t._function_data


def test_do_not_trace_generators():
    """
    If a generator function returns a Deferred, nothing happens. More
    specifically, no function trace information is stored.
    """
    t = Tracer()
    t._trace(
        FakeFrame(FakeCode(flags=inspect.CO_GENERATOR)),
        'return', defer.Deferred())
    assert not t._function_data


def test_do_not_trace_defer_module():
    """
    If a function in twisted.internet.defer returns a Deferred, nothing
    happens. More specifically, no function trace information is stored.
    """
    t = Tracer()
    t._trace(
        FakeFrame(globals={'__name__': 'twisted.internet.defer'}),
        'return', defer.Deferred())
    assert not t._function_data


_frame_spam = FakeFrame(FakeCode('spam.py', 'spam'))
_frame_eggs = FakeFrame(FakeCode('eggs.py', 'eggs'), _frame_spam)
_frame_unwindGenerator = FakeFrame(
    FakeCode('defer.py', 'unwindGenerator'),
    _frame_eggs,
    {'__name__': 'twisted.internet.defer'},
    {'f': FakeFunction(FakeCode('sausage.py', 'sausage'))})


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
    tracer._trace(frame, 'call', None)
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


def test_trace_inlineCallbacks_detection():
    """
    Tracer will detect the use of inlineCallbacks and rewrite the call stacks
    to look better and contain more information.
    """
    clock = task.Clock()
    t = Tracer(reactor=clock)
    _trace_deferred_firing_after(clock, t, _frame_unwindGenerator, 0.5)
    assert t._function_data == {
        ('spam.py', 'spam'): ({
            ('eggs.py', 'eggs'): (1, 500000),
        }, 0),
        ('eggs.py', 'eggs'): ({
            ('sausage.py', 'sausage'): (1, 500000),
        }, 0),
        ('sausage.py', 'sausage'): ({}, 500000),
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

    def setprofile(self, trace):
        self.tracer = trace

    def getprofile(self):
        return self.tracer


@pytest.fixture
def fakesys(monkeypatch):
    fakesys = FakeSys()
    monkeypatch.setattr('theseus._tracer.sys', fakesys)
    return fakesys


def test_tracer_install(fakesys):
    """
    Tracer's install method will install itself globally using sys.setprofile.
    """
    t = Tracer()
    t.install()
    assert fakesys.tracer == t._trace


def test_tracer_wrapped_hook(fakesys):
    """
    If a profile hook was set prior to calling Tracer's install method, it will
    continue to be called by Tracer.
    """
    calls = []

    def tracer(frame, event, arg):
        calls.append((frame, event, arg))
    fakesys.tracer = tracer
    t = Tracer()
    t.install()
    sentinel = object()
    t._trace(sentinel, 'call', sentinel)
    assert calls == [(sentinel, 'call', sentinel)]


def test_tracer_uninstall(fakesys):
    """
    Tracer's install method will uninstall itself as well.
    """
    t = Tracer()
    t.install()
    t.uninstall()
    assert fakesys.tracer is None


def test_tracer_uninstall_with_other_hook(fakesys):
    """
    If another profile hook was installed after the Tracer was installed, then
    the profile hook will remain unchanged.
    """
    t = Tracer()
    t.install()
    fakesys.tracer = sentinel = object()
    t.uninstall()
    assert fakesys.tracer is sentinel


def test_tracer_uninstall_with_other_hook_previously_installed(fakesys):
    """
    If another profile hook was installed before the Tracer was installed, then
    the profile hook will be restored to that profile hook.
    """
    t = Tracer()
    fakesys.tracer = sentinel = object()
    t.install()
    t.uninstall()
    assert fakesys.tracer is sentinel
