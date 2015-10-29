# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

from __future__ import print_function

from distutils.command.build_ext import build_ext
import platform
import sys

from setuptools import Extension, setup


ext_modules = []
if platform.python_implementation() == 'CPython':
    speedups = Extension('theseus._cytracer', [])
    try:
        from Cython.Distutils import build_ext
    except ImportError:
        import traceback
        print('** WARNING: Cython not found: **', file=sys.stderr)
        traceback.print_exc()
        print('** END WARNING **', file=sys.stderr)
        speedups.sources.append('theseus/_cytracer.c')
    else:
        speedups.sources.append('theseus/_cytracer.pyx')
    ext_modules.append(speedups)


with open('README.rst', 'r') as infile:
    long_description = infile.read()


setup(
    name='twisted-theseus',
    description='a Deferred-aware profiler for Twisted',
    long_description=long_description,
    author='Aaron Gallagher',
    author_email='_@habnab.it',
    url='https://github.com/flowroute/twisted-theseus',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Framework :: Twisted',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: ISC License (ISCL)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development',
    ],
    license='ISC',

    vcversioner={
        'version_module_paths': ['theseus/_version.py'],
    },
    packages=['theseus', 'theseus.test'],
    ext_modules=ext_modules,
    setup_requires=['vcversioner'],
    install_requires=['Twisted'],
    cmdclass=dict(build_ext=build_ext),
    zip_safe=False,
)
