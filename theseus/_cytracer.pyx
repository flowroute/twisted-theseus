# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

from cpython.ref cimport PyObject
from twisted.internet import defer

from theseus._tracer import FakeFrame, Tracer

cdef extern from "code.h":
    ctypedef struct PyCodeObject:
        int co_flags
        PyObject *co_name

    int CO_GENERATOR

cdef extern from "frameobject.h":
    ctypedef struct PyFrameObject:
        PyObject *f_globals
        PyObject *f_locals
        PyObject *f_back
        PyCodeObject *f_code

    void PyFrame_FastToLocals(PyFrameObject *)
    void PyFrame_LocalsToFast(PyFrameObject *, int)

cdef extern from "pystate.h":
    ctypedef int (*Py_tracefunc)(PyObject *, PyFrameObject *, int, PyObject *) except -1

    ctypedef struct PyThreadState:
        Py_tracefunc c_profilefunc
        PyObject *c_profileobj

    PyThreadState *PyThreadState_GET()
    int PyTrace_RETURN

cdef extern from "ceval.h":
    void PyEval_SetProfile(Py_tracefunc, PyObject *)


cdef int theseus_tracefunc(PyObject *_self, PyFrameObject *_frame, int event, PyObject *_arg) except -1:
    cdef CythonTracer self = <CythonTracer>_self
    cdef object arg = None if _arg is NULL else <object>_arg
    cdef object frame = <object>_frame
    if self.prev_profilefunc is not NULL:
        self.prev_profilefunc(<PyObject *>self.prev_profileobj, _frame, event, _arg)

    if event != PyTrace_RETURN:
        return 0

    # Don't care about generators; inlineCallbacks is handled separately.
    if _frame.f_code.co_flags & CO_GENERATOR:
        return 0

    # If it's not a deferred, we don't care either.
    if not isinstance(arg, defer.Deferred):
        return 0

    # Tracing functions from twisted.internet.defer adds a lot of noise, so
    # don't do that except for unwindGenerator.
    if (<object>_frame.f_globals).get('__name__') == 'twisted.internet.defer':
        # Detect when unwindGenerator returns. unwindGenerator is part of the
        # inlineCallbacks implementation. If unwindGenerator is returning, it
        # means that the Deferred being returned is the Deferred that will be
        # returned from the wrapped function. Yank the wrapped function out and
        # fake a call stack that makes it look like unwindGenerator isn't
        # involved at all and the wrapped function is being called
        # directly. This /does/ involve Twisted implementation details, but as
        # far back as twisted 2.5.0 (when inlineCallbacks was introduced), the
        # name 'unwindGenerator' and the local 'f' are the same. If this ever
        # changes in the future, I'll have to update this code.
        if (<object>_frame.f_code.co_name) == 'unwindGenerator':
            PyFrame_FastToLocals(_frame)
            try:
                wrapped_func = (<object>_frame.f_locals)['f']
            finally:
                PyFrame_LocalsToFast(_frame, 1)
            frame = FakeFrame(
                wrapped_func.func_code,
                None if _frame.f_back is NULL else <object>_frame.f_back)
        else:
            return 0

    key = frame, arg
    self.wrapped_tracer._deferreds[key] = self.wrapped_tracer._reactor.seconds()
    arg.addBoth(self.wrapped_tracer._deferred_fired, key)
    return 0


cdef class CythonTracer:
    cdef Py_tracefunc prev_profilefunc
    cdef object prev_profileobj
    cdef object wrapped_tracer

    def __cinit__(self):
        self.prev_profilefunc = NULL
        self.wrapped_tracer = Tracer()

    def __dealloc__(self):
        cdef PyThreadState *thread_state = PyThreadState_GET()
        if thread_state.c_profileobj == <PyObject *>self:
            self.uninstall()

    def install(self):
        """
        Install this tracer as a global `profile hook
        <https://docs.python.org/2/library/sys.html#sys.setprofile>`_.

        The old profile hook, if one is set, will continue to be called by this
        tracer.
        """
        cdef PyThreadState *thread_state = PyThreadState_GET()
        if thread_state.c_profilefunc is not NULL:
            self.prev_profilefunc = thread_state.c_profilefunc
            self.prev_profileobj = <object>thread_state.c_profileobj
        PyEval_SetProfile(theseus_tracefunc, <PyObject *>self)

    def uninstall(self):
        """
        Deactivate this tracer.

        If another profile hook was installed after this tracer was installed,
        nothing will happen. If a different profile hook was installed prior to
        calling ``install()``, it will be restored.
        """
        cdef PyThreadState *thread_state = PyThreadState_GET()
        if thread_state.c_profileobj != <PyObject *>self:
            return
        if self.prev_profilefunc is not NULL:
            PyEval_SetProfile(self.prev_profilefunc, <PyObject *>self.prev_profileobj)
        else:
            PyEval_SetProfile(NULL, NULL)
        self.prev_profilefunc = NULL
        self.prev_profileobj = None

    def write_data(self, fobj):
        """
        Write profiling data in `callgrind format
        <http://valgrind.org/docs/manual/cl-format.html>`_ to an open file
        object.

        The file object will not be closed.
        """
        self.wrapped_tracer.write_data(fobj)
