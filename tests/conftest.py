"""Keep one Qt application alive across all in-process widget tests."""
import os
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@pytest.fixture(scope='session', autouse=True)
def qt_application():
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    # A test-local reference can be collected while a later fixture constructs
    # widgets. Qt permits only one QApplication lifetime per test process.
    yield application
