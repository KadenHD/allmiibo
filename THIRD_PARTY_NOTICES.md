# Third-party notices

Allmiibo Manager is licensed under the MIT License. The Windows executable also
contains or is produced with third-party software governed by its own license
terms. Those terms remain controlling for the corresponding components.

## Runtime components

### Bleak

- Purpose: Bluetooth Low Energy client.
- License: MIT License.
- Copyright: Copyright (c) 2020 Henrik Blidh.
- Source and license: <https://github.com/hbldh/bleak>

### Qt for Python: PySide6 Essentials and Shiboken6

- Purpose: graphical interface and Python bindings for Qt.
- Release constraint used by this project: 6.8.3.
- Community licensing: GNU Lesser General Public License v3 and GNU General
  Public License v3 options; individual files may carry additional compatible
  terms. This project distributes the community build under the LGPL option.
- License information: <https://doc.qt.io/qtforpython-6/licenses.html>
- Qt licensing overview: <https://doc.qt.io/qt-6/licensing.html>
- Source: <https://code.qt.io/cgit/pyside/pyside-setup.git/>

The application source, build specification, and pinned Qt for Python version
are included in this repository so recipients can rebuild the application with
a compatible or modified Qt library. No Qt source file is modified by this
project.

### Python

- Purpose: embedded Python runtime and standard library.
- Runtime series: Python 3.12.
- License: Python Software Foundation License Version 2 and the additional
  historical notices applicable to included Python releases.
- License information and source: <https://docs.python.org/3/license.html>

## Build and packaging component

### PyInstaller

- Purpose: creation of the standalone Windows executable.
- Release constraint used by this project: 6.x.
- License: GNU General Public License v2 or later with the PyInstaller
  bootloader exception. Runtime hooks can use Apache License 2.0 or other terms
  identified in their source files.
- Source and complete license text:
  <https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt>

The PyInstaller bootloader exception permits distribution of applications
created with PyInstaller without requiring the bundled application itself to
use the GPL solely because it was packaged with PyInstaller.

## Platform runtime

The Windows package can include Microsoft Visual C++ runtime libraries. These
are Microsoft redistributable components, not open-source software, and remain
subject to Microsoft's applicable distribution terms.

## Rebuilding

The complete Allmiibo Manager source and build instructions are available in
this repository. See `README.md`, `requirements-build.txt`, and
`AllmiiboManager.spec` to create a new executable from source.

This notice is provided for attribution and convenience. Consult the upstream
license texts for the complete and authoritative terms.
