def generate_words(language='english', count=24):
    from mnemonic import Mnemonic
    mnemonic = Mnemonic(language)
    return mnemonic.generate(strength=int(count*10.67))


def create_parser():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--language', help='Words language')
    parser.add_argument('--count', type=int, help='Word count')
    return parser


def execute(args):
    kwargs = {}

    if args.language:
        kwargs['language'] = args.language
    if args.count:
        kwargs['count'] = args.count

    print(generate_words(**kwargs))


def main():
    parser = create_parser()
    args = parser.parse_args()
    execute(args)


if __name__ == '__main__':
    main()
