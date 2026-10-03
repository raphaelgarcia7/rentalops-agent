"""Private operator commands. Run in a terminal without recording its output."""

import argparse
import sys

from sqlalchemy.exc import SQLAlchemyError

from rentalops_api.auth import AuthError, AuthService, AuthSettings
from rentalops_api.config import DatabaseSettings
from rentalops_api.database import build_engine, build_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "create-user",
            "issue-access-link",
            "issue-reset-link",
            "deactivate-user",
        ],
    )
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    engine = None
    try:
        settings = AuthSettings.from_environment()
        engine = build_engine(DatabaseSettings.from_environment())
        service = AuthService(build_session_factory(engine), settings)
        if args.command == "create-user":
            user_id, created = service.create_user(args.email)
            print(f"{'created' if created else 'existing'} user_id={user_id}")
        elif args.command == "deactivate-user":
            print(f"deactivated user_id={service.deactivate(args.email)}")
        else:
            token = service.issue_link(
                args.email, "access" if args.command == "issue-access-link" else "reset"
            )
            # This is the only intentional private token output, for manual delivery.
            print(f"{settings.origin}/definir-senha#token={token}")
    except AuthError as error:
        print(error.message, file=sys.stderr)
        raise SystemExit(1) from None
    except ValueError, SQLAlchemyError:
        print(
            "Command failed. Check configuration and database availability.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
