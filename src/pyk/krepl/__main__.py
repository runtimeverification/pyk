from argparse import ArgumentParser

from .repl import Repl


def main() -> None:
    argument_parser().parse_args()
    try:
        Repl().cmdloop()
    except KeyboardInterrupt:
        ...


def argument_parser() -> ArgumentParser:
    return ArgumentParser(description='K-REPL Client')


if __name__ == '__main__':
    main()
