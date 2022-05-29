#!/usr/bin/env python3
from game.action import Action, Move
from game.board import Board
from game.artificial_agent import ArtificialAgent
from argparse import ArgumentParser, Namespace
from importlib.util import spec_from_file_location, module_from_spec
from os.path import join as path_join
from os.path import dirname, exists
from typing import List, Optional, Tuple

AGENTS_DIR = path_join(dirname(__file__), "agents")
LEVELS_DIR = path_join(dirname(__file__), "game", "levels")

parser = ArgumentParser()
parser.add_argument(
    "level_set", type=str, help="Name of set of levels to play. (without .sok)"
)
parser.add_argument("-l", "--level", type=int, help="Level number to play.")
parser.add_argument(
    "-n", "--num_levels", type=int, help="Number of levels to play."
)
parser.add_argument(
    "-a",
    "--agent",
    default=None,
    type=str,
    help=(
        "Agent to use, should be name of class in the file lowercase.py,"
        " in the same directory as this script. (default player)"
    ),
)
parser.add_argument(
    "-o",
    "--optimal",
    default=False,
    action="store_true",
    help="Require move-optimal solution. (Omitted when player plays.)",
)
parser.add_argument(
    "--max_fail",
    default=0,
    type=int,
    help="Maximum level failures allowed. (Omitted when player plays.)",
)
parser.add_argument(
    "-v",
    "--verbose",
    default=False,
    action="store_true",
    help="Verbose output. (Omitted when player plays.)",
)
parser.add_argument(
    "--visualize",
    default=False,
    action="store_true",
    help="Graphical simulation.",
)


def process_args(
    args: Optional[List[str]] = None,
) -> Tuple[ArtificialAgent, str, Namespace]:
    """Parse arguments, check validity and return usefull values."""
    if args is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(args)

    if args.level and args.level < 1:
        parser.error("Invalid level number.")

    if args.num_levels and args.num_levels < 1:
        parser.error("Invalid number of levels to play.")

    if args.num_levels is None:
        if args.level is not None:
            args.num_levels = 1
        else:
            args.num_levels = -1

    agent = None
    if args.agent:
        try:
            spec = spec_from_file_location(
                f"agents.{str.lower(args.agent)}",
                path_join(AGENTS_DIR, f"{str.lower(args.agent)}.py"),
            )
            am = module_from_spec(spec)
            spec.loader.exec_module(am)
            agent: ArtificialAgent = getattr(am, args.agent)()
        except BaseException as e:
            parser.error(f"Invalid agent name:\n{str(e)}")

        agent.verbose = args.verbose
        agent.optimal = args.optimal

    file = path_join(LEVELS_DIR, args.level_set + ".sok")
    if not exists(file):
        parser.error("Invalid level - file does not exist.")
    return agent, file, args


def get_board(file: str, level: int, skip: int) -> Tuple[Board, int]:
    board, min_moves, skip = Board.from_file(file, level, skip=skip)

    return board, min_moves


def sim(agent: ArtificialAgent, file: str, args: Namespace, gui):
    verbose = args.verbose
    skips: List[int] = [0]
    total_time = 0
    total_losses = 0
    level_count = 0
    print(
        "Playing sokoban: set {}, {}".format(
            args.level_set,
            f"level {args.level}" if args.level is not None else "all levels",
        )
    )
    levels_running = True
    reset = False
    next_level = args.level
    while levels_running:
        if args.num_levels == level_count:
            break

        if gui:
            gui.close()

        moves = 0
        if reset:
            board, min_moves, skip = Board.from_file(
                file, next_level - 1, skip=skips[-2]
            )
        else:
            board, min_moves, skip = Board.from_file(
                file, next_level, skip=skips[-1]
            )

        if board is None:
            break

        if not reset:
            skips.append(skip)
            next_level = board.level + 1
        reset = False

        if verbose:
            if args.level is None or gui is not None:
                print(f"Level {board.level_name}")

            if args.optimal and min_moves == -1:
                print("Optimality can't be checked.")

        # AGENT
        action = None
        if agent:
            agent.new_game()
            agent.observe(board)

            # let agent think before initializing GUI
            print("Agent thinking.")
            action = agent.act()
            if not verbose:
                print("Thinking done.")

        if gui:
            gui.new_board(board)
            if agent:
                if not gui.wait_next():
                    break

        actions: List[Action] = []

        # GAME LOOP
        while True:
            # VICTORY
            if board.is_victory():
                if not gui:
                    if verbose:
                        print(
                            f" solved in {agent._think_time:.2f} s and {moves} moves"
                        )
                    if args.optimal and min_moves != -1 and min_moves < moves:
                        if verbose:
                            print(
                                "Solution is not optimal: {}x{} moves".format(
                                    moves, min_moves
                                )
                            )
                        total_losses += 1

                if agent:
                    total_time += agent._think_time
                break

            # MOVE
            rev = False
            if agent:
                action = agent.act() if action is None else action
                if action is None:
                    # agent gave up
                    if verbose:
                        print(f" agent gave up after {agent._think_time:.2f} s")
                    total_losses += 1
                    total_time += agent._think_time
                    break
                if not action.is_possible(board):
                    raise RuntimeError("Agent returned illegal move!")
            else:
                # NO AGENT
                end_current_game = False
                while True:
                    sign, action = gui.choose_direction(bool(actions))
                    if sign == 1:
                        action = Move.or_push(board, action)
                        if action.is_possible(board):
                            break
                    elif sign == -1:
                        levels_running = False
                        end_current_game = True
                        break
                    elif sign == 0:
                        reset = True
                        end_current_game = True
                        break
                    elif sign == 2:
                        rev = True
                        action = actions.pop()
                        break
                if end_current_game:
                    break

            if rev:
                moves -= 1
                action.reverse(board)
            else:
                actions.append(action)
                moves += 1
                action.perform(board)

            # DRAW
            if gui:
                if not gui.draw_and_wait(board, bool(agent)):
                    levels_running = False
                    break
            action = None
        if not reset:
            level_count += 1
    if agent:
        print(
            "Average thinking time in {} levels: {:.1f} s\nSolved {}/{}.".format(
                level_count,
                total_time / level_count,
                level_count - total_losses,
                level_count,
            )
        )


def main(args_list: list = None) -> None:
    agent, file, args = process_args(args_list)

    gui = None
    if not agent or args.visualize:
        from game.sokoban_gui import SokobanGUI

        gui = SokobanGUI()

    sim(agent, file, args, gui)
    # sim = Simulator(agent, file, args, gui)
    # sim.sim()


if __name__ == "__main__":
    # if you don't want to specify arguments for the script you can also
    # call main with desired arguments in list
    # e.g. main(["easy"]),
    # main(["Aymeric_Hard", "-l=3", "-a=Agent", "--visualize"])
    main()