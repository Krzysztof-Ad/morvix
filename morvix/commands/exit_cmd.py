# exit command - signals the shell loop to stop

NAME = "exit"


def configure(parser):
    pass


def run(ctx, args):
    ctx.should_exit = True
    if ctx.interactive:
        ctx.messenger.plain("Goodbye.")
    return 0
