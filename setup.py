# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

from setuptools import setup


with open('README.rst', 'r') as infile:
    long_description = infile.read()


setup(
    name='twisted-theseus',
    description='a Deferred profiler',
    long_description=long_description,
    author='Aaron Gallagher',
    author_email='_@habnab.it',
    url='https://github.com/habnabit/twisted-theseus',
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
    setup_requires=['vcversioner'],
    install_requires=['Twisted'],
    zip_safe=False,
)
