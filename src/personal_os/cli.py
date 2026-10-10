import argparse
import json
import sys
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="Local personal data for MCP Agents")
    parser.add_argument("--vault", required=True, help="Explicit path to your private local vault")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    serve = sub.add_parser("serve")
    serve.add_argument("--allow-restricted", action="store_true", help="Expose restricted records to this Agent")
    sub.add_parser("proposals")
    show = sub.add_parser("show-proposal")
    show.add_argument("id")
    for name in ("approve", "reject"):
        command = sub.add_parser(name)
        command.add_argument("id")
    delete = sub.add_parser("delete")
    delete.add_argument("id")
    delete.add_argument("--revision", required=True, type=int)
    restore = sub.add_parser("restore")
    restore.add_argument("id")
    restore.add_argument("--revision", required=True, type=int)
    args = parser.parse_args()
    store = Store(args.vault)
    try:
        if args.command == "serve":
            if not store.meta.is_dir():
                raise ValueError("Run init first")
            from .server import create_server
            create_server(args.vault, args.allow_restricted).run(transport="stdio")
            return
        if args.command == "init":
            store.init()
            result = {"initialized": True, "vault": str(store.root)}
        elif args.command == "proposals":
            result = [{"id": p["id"], "title": p["record"]["title"], "state": p["state"]} for p in store.proposals()]
        elif args.command == "show-proposal":
            result = next((p for p in store.proposals() if p["id"] == args.id), None)
            if result is None:
                raise ValueError("Proposal not found")
        elif args.command in ("approve", "reject"):
            result = store.review(args.id, args.command == "approve")
        elif args.command == "delete":
            result = store.delete(args.id, args.revision)
        else:
            result = store.restore(args.id, args.revision)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        print(f"Personal OS: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
