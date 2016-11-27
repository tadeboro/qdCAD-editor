Installation
============

This document describes how to install qdCAD editor on various platforms.


GNU/Linux
---------

Installation on GNU/Linux is really straight-forward. Use your favourite
package manager to install ``python3-gobject`` or ``python3-gi`` package and
you are done with preprequisites. Just make sure you installed package for
Python version 3.

Now download the editor sources from `project's Github repo`_ and move to
folder ``qdcad_editor``. Now execute ``python3 main.py`` and start editing.

.. _project's Github repo: https://github.com/tadeboro/qdCAD-editor


MS Windows
----------

Installing GObject bindings for python on Windows is a bit involved, so we
provide a complete package at `download site`_ that includes everything that
is needed to run the editor: python interpreter, GTK+ libraries, introspection
files and python bindings. Simply download the package, unzip it and run
``qdcad-edit.bat``.

.. _download site: http://x.k00.fr/1xqk6
