.. image:: https://travis-ci.org/flowroute/twisted-theseus.png


=================
 twisted-theseus
=================

A Deferred_-aware profiler for Python code.

While cProfile_ is a very useful utility,
it is limited to recording *synchronous* execution time.
A function that returns a Deferred will typically return very quickly,
while the Deferred it returns might not fire for seconds or even minutes.
This is where theseus comes in:
any function that returns a Deferred will be tracked by theseus.
The time from when the Deferred was returned to when it fired will be measured,
and recorded along with the function's call stack.


Usage
=====

The public interface of theseus is a class called ``Tracer``.
To get started::

  from theseus import Tracer
  t = Tracer()
  t.install()

This is enough to start tracing execution.
Eventually, the statistics will have to be written to disk::

  with open('callgrind.theseus', 'wb') as outfile:
    t.write_data(outfile)

The output is written in `callgrind format`_,
which means that standard tools can be used to interpret the results,
such as kcachegrind_.

If at any point the ``Tracer`` is no longer useful,
it can be uninstalled to stop tracing::

  t.uninstall()

Additionally,
theseus is aware of inlineCallbacks_,
and will rewrite call stacks to make them look "correct".
For example,
given this code::

  from twisted.internet import defer, task

  @defer.inlineCallbacks
  def func(reactor):
    yield task.deferLater(reactor, 1, lambda: None)

  task.react(func)

The call stack according to theseus will look like this (most recent call last)::

  __main__ in <module>
  twisted.internet.task in react
  __main__ in func

While theseus and cProfile both use a `profile hook`_,
as long as cProfile is installed first,
both profilers can be used at the same time.
In this case,
calling ``uninstall()`` will restore cProfile.


.. _Deferred: https://twistedmatrix.com/documents/current/core/howto/defer.html
.. _cProfile: https://docs.python.org/2/library/profile.html
.. _callgrind format: http://valgrind.org/docs/manual/cl-format.html
.. _kcachegrind: http://kcachegrind.sourceforge.net/html/Home.html
.. _inlineCallbacks: http://twistedmatrix.com/documents/current/api/twisted.internet.defer.html#inlineCallbacks
.. _profile hook: https://docs.python.org/2/library/sys.html#sys.setprofile
