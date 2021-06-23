import tempfile

from hathor.cli.shell import Shell
from tests import unittest


class ShellTest(unittest.TestCase):
    # In this case we just want to go through the code to see if it's okay

    def test_shell_execution_memory_storage(self):
        shell = Shell(argv=['--memory-storage'])
        self.assertTrue(shell is not None)

    def test_shell_execution_default_storage(self):
        temp_data = tempfile.TemporaryDirectory()
        shell = Shell(argv=['--data', temp_data.name])
        self.assertTrue(shell is not None)
