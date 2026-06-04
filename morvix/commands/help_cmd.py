# STUB - to be implemented. Command contract (see morvix/registry.py):
#   NAME, configure(parser), run(ctx, args) -> int, optional complete(...)

NAME = 'help'


def configure(parser):
    pass


def run(ctx, args):
    ctx.messenger.warning("'help' is not implemented yet.")
    return 0
