# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

from setuptools import setup


setup(
    name='twisted-theseus',
    author='Aaron Gallagher',
    author_email='_@habnab.it',
    url='https://github.com/habnabit/twisted-theseus',
    license='ISC',

    vcversioner={
        'version_module_paths': ['theseus/_version.py'],
    },
    packages=['theseus'],
    setup_requires=['vcversioner'],
    zip_safe=False,
)
