from tests import unittest
from hathor.cli.generate_valid_words import create_parser, execute

from io import StringIO
from contextlib import redirect_stdout


class GenerateWordsTest(unittest.TestCase):
    def test_generate_words(self):
        parser = create_parser()

        # Default generation of words (24 words in english)
        args = parser.parse_args([])
        f = StringIO()
        with redirect_stdout(f):
            execute(args)
        # Transforming prints str in array
        output = f.getvalue().split('\n')
        # Last element is always empty string
        output.pop()

        self.assertEqual(len(output[0].split(' ')), 24)

        # Generate 18 words
        params = ['--count', '18']
        args = parser.parse_args(params)
        f = StringIO()
        with redirect_stdout(f):
            execute(args)
        # Transforming prints str in array
        output = f.getvalue().split('\n')
        # Last element is always empty string
        output.pop()

        self.assertEqual(len(output[0].split(' ')), 18)

        # Generate 18 japanese words
        params = ['--count', '18', '--language', 'japanese']
        args = parser.parse_args(params)
        f = StringIO()
        with redirect_stdout(f):
            execute(args)
        # Transforming prints str in array
        output = f.getvalue().split('\n')
        # Last element is always empty string
        output.pop()

        # In japanese is more than 18 when I split by space
        self.assertNotEqual(len(output[0].split(' ')), 18)
