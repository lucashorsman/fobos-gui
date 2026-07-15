"""Launch the FOBOS GUI with mock positioners (FOBOS_MOCK=1)."""
import os

os.environ.setdefault("FOBOS_MOCK", "1")


from main import main  # noqa: E402

if __name__ == "__main__":
    main()
