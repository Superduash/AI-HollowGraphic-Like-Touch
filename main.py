"""Root launcher so `python main.py` works from project directory."""


def main() -> None:
    # Import lazily so this file stays a lightweight entrypoint.
    from src.main import run

    run()


if __name__ == "__main__":
    main()
