from tempfile import NamedTemporaryFile
from unittest import TestCase

from pyk.kllvm.parser import Parser


class ParserTest(TestCase):
    def test_file(self) -> None:
        # Given
        text = """
            A{}(
                B{}(),
                C{}()
            )
        """

        with NamedTemporaryFile(mode='w') as f:
            f.write(text)
            f.flush()

            parser = Parser(f.name)

            # When
            actual = parser.pattern()

        # Then
        self.assertEqual(str(actual), 'A{}(B{}(),C{}())')

    def test_string(self) -> None:
        # Given
        parser = Parser.from_string('A{}(X:S, Y:Z, Int{}())')

        # When
        actual = parser.pattern()

        # Then
        self.assertEqual(str(actual), 'A{}(X : S,Y : Z,Int{}())')
