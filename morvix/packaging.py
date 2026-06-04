# Packaging and the package format (Section 19).
#
# Assembles a single shareable archive with everything a Receiver needs and
# nothing the Author wants kept private: tests, expected answers, the runner,
# the generated README and the manifest - but never the solution source or the
# brute-force reference. run.sh is placed at the archive root so the habitual
# ./run.sh works on a clean machine.
#
# API (implement in Workflow B):
#   build_package(ctx, project, fmt="zip", runners=None,
#                 include_generators=False, out=None) -> str   # archive path
#   estimate_size(project) -> int   # bytes, for the large-package suggestion


def build_package(ctx, project, fmt="zip", runners=None, include_generators=False, out=None):
    raise NotImplementedError


def estimate_size(project):
    raise NotImplementedError
