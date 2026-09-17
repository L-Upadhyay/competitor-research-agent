# Entry point: runs the competitor research agent interactively in the terminal.
#
# Usage:
#   uv run python main.py
#   uv run python main.py --fail Brex    (demo: make every search mentioning "Brex" fail)

import argparse
import os


def ask_human(payload):
    """Show what the agent is asking and return the human's typed answer."""
    kind = payload.get("kind")
    print()
    if kind == "approve_brief":
        print("=" * 60)
        print(payload.get("brief", ""))
        print("=" * 60)
    print(payload.get("message", "The agent needs your input."))
    prompt = {"clarify": "Your answer: ", "confirm_competitors": "Competitors: ", "approve_brief": "approve / reject: "}
    return input(prompt.get(kind, "> "))


def run():
    parser = argparse.ArgumentParser(description="Competitor Research Agent")
    parser.add_argument("--fail", metavar="NAME", help="demo: simulate search failures for queries containing NAME")
    args = parser.parse_args()

    if args.fail:
        os.environ["FAIL_SEARCH_FOR"] = args.fail
        print(f"(demo) searches mentioning \"{args.fail}\" will fail")

    company = input("Company to research: ").strip()
    if not company:
        print("No company entered. Nothing to do.")
        return
    context = input("Optional context (e.g. what the company does), or press Enter to skip: ").strip()

    # Import here so a missing package or key problem is caught by the friendly error handler below.
    from langgraph.types import Command

    from agent.graph import build_graph, initial_state, make_config

    graph = build_graph()
    config = make_config()

    # Run until the graph pauses for a human, answer, and resume. Repeat until it finishes.
    result = graph.invoke(initial_state(company, context), config)
    while result.get("__interrupt__"):
        answer = ask_human(result["__interrupt__"][0].value)
        result = graph.invoke(Command(resume=answer), config)

    final = graph.get_state(config).values
    print()
    if final.get("saved_path"):
        print(f"Brief saved to: {final['saved_path']}")
    else:
        print("The brief was not saved.")


def main():
    try:
        run()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Nothing was saved.")
    except Exception as e:
        print(f"\nSorry, something went wrong and the run stopped: {e.__class__.__name__}: {e}")
        print("Check your API keys in .env and your internet connection, then try again.")


if __name__ == "__main__":
    main()
