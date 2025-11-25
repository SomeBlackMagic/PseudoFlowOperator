import argparse
import logging
import os


def main():
    parser = argparse.ArgumentParser(description="PseudoFlow Operator")
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (overrides --log-level to DEBUG)",
    )
    args = parser.parse_args()

    level_name = "DEBUG" if args.debug else args.log_level.upper()
    os.environ["LOG_LEVEL"] = level_name
    if args.debug:
        os.environ["DEBUG"] = "true"

    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger(__name__).info(
        "Starting PseudoFlow operator with level %s", level_name
    )

    from .main import main as operator_main

    operator_main()
