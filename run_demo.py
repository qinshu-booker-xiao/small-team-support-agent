#!/usr/bin/env python3
"""Interactive Terminal CLI Demo with Persona Switcher for small-team-support-agent.

Allows interacting with the multi-persona tennis support team:
- Gina (Player)
- Gor (Head Coach)
- Sai (Tactical Coach)
- Ma (PT & Nutritionist)
- Beita (Personal Assistant & PR)
- Coordinator (Master Dispatcher)
"""

import os
import sys

# Ensure local package path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agent import extract_persona, run_turn
from app.engine import calendar_store
from app.tools import get_daily_schedule, reset_store_state


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"


PERSONA_COLORS = {
    "coordinator": Colors.CYAN,
    "gor": Colors.YELLOW,
    "sai": Colors.BLUE,
    "ma": Colors.GREEN,
    "beita": Colors.HEADER,
    "gina": Colors.GREEN,
}

PERSONA_ICONS = {
    "coordinator": "👔",
    "gor": "🎾",
    "sai": "📋",
    "ma": "🏋️",
    "beita": "📸",
    "gina": "⭐",
}


def print_banner():
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}🎾 SMALL TEAM SUPPORT AGENT: MULTI-PERSONA INTERACTIVE DEMO{Colors.RESET}")
    print(f"{Colors.CYAN}Digital Chief-of-Staff for WTA Player Gina & Support Team (ADK 2.0){Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print("Available Commands:")
    print("  /persona <gina|gor|sai|ma|beita|coordinator> - Switch active persona")
    print("  /schedule [YYYY-MM-DD]                        - View team agenda & active alerts")
    print("  /reset                                        - Reset simulation state to 09/01 seed")
    print("  /quick <1-11>                                 - Run quick simulation test case (TC-01..11)")
    print("  /help                                         - Show this guide")
    print("  /exit or quit                                 - Exit demo")
    print(f"{Colors.CYAN}{'-'*80}{Colors.RESET}\n")


def execute_quick_scenario(tc_num: int, current_persona: str) -> str:
    """Run predefined verification scenarios via agent turns."""
    scenarios = {
        1: ("gina", "What is my schedule for tomorrow (2026-09-02)?"),
        2: ("gor", "Schedule a 2.5 hour serve training session on 2026-09-02 at 14:00"),
        3: ("gor", "Schedule 90-min training on 2026-09-02 at 14:30"),
        4: ("ma", "Workout syllabus for 2026-09-02: Core stability and hip mobility with resistance bands"),
        5: ("ma", "Meal plan for 2026-09-02: Breakfast oatmeal with berries, lunch grilled chicken quinoa, dinner salmon salad"),
        6: ("beita", "Book sponsor meet-and-greet on 2026-09-02 at 11:00 AM"),
        7: ("gor", "Schedule court training on 2026-09-03 at 10:00 AM"),
        8: ("sai", "Book opponent tactical analysis on 2026-09-03 for Sofia Kenin match"),
        9: ("gina", "What is my schedule for match day (2026-09-04)?"),
        10: ("beita", "Book brand interview on 2026-09-04 at 17:00"),
        11: ("gor", "Schedule court training on 2026-09-02 at 16:30 for 60 minutes"),
    }

    if tc_num not in scenarios:
        return f"Unknown quick test number {tc_num}. Choose 1 through 11."

    target_persona, prompt = scenarios[tc_num]
    print(f"{Colors.BOLD}[Quick Run TC-{tc_num:02d}]{Colors.RESET} Sending as {target_persona.upper()}: '{prompt}'")
    return run_turn(f"[As {target_persona.capitalize()}] {prompt}", persona=target_persona)


def main():
    print_banner()
    current_persona = "coordinator"

    while True:
        color = PERSONA_COLORS.get(current_persona, Colors.CYAN)
        icon = PERSONA_ICONS.get(current_persona, "👤")
        prompt_label = f"{color}{Colors.BOLD}[{icon} {current_persona.upper()}]{Colors.RESET}> "

        try:
            user_input = input(prompt_label).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.CYAN}Exiting Small Team Support Agent demo. Goodbye!{Colors.RESET}")
            break

        if not user_input:
            continue

        cmd_lower = user_input.lower()

        # Handle built-in slash commands
        if cmd_lower in ("/exit", "exit", "quit", "q"):
            print(f"{Colors.CYAN}Exiting Small Team Support Agent demo. Goodbye!{Colors.RESET}")
            break

        if cmd_lower in ("/help", "help"):
            print_banner()
            continue

        if cmd_lower.startswith("/persona"):
            parts = user_input.split()
            if len(parts) > 1 and parts[1].lower() in PERSONA_COLORS:
                current_persona = parts[1].lower()
                print(f"Switched persona to {Colors.BOLD}{current_persona.upper()}{Colors.RESET}.\n")
            else:
                print("Usage: /persona <gina|gor|sai|ma|beita|coordinator>\n")
            continue

        if cmd_lower.startswith("/schedule"):
            parts = user_input.split()
            target_date = parts[1] if len(parts) > 1 else "2026-09-02"
            print(calendar_store.format_daily_agenda_and_alerts(target_date))
            print()
            continue

        if cmd_lower == "/reset":
            reset_store_state()
            print(f"{Colors.GREEN}Simulation state reset to reference date 2026-09-01.{Colors.RESET}\n")
            continue

        if cmd_lower.startswith("/quick"):
            parts = user_input.split()
            if len(parts) > 1 and parts[1].isdigit():
                tc_num = int(parts[1])
                response = execute_quick_scenario(tc_num, current_persona)
                print(f"\n{Colors.BOLD}Agent Response:{Colors.RESET}\n{response}\n")
            else:
                print("Usage: /quick <1-11>\n")
            continue

        # Handle interactive HITL keywords directly if desired
        if user_input.strip() in ("[Approve]", "[Approve Override]", "approve", "yes", "confirm"):
            res = calendar_store.approve_pending_proposal()
            print(f"\n{Colors.GREEN}{Colors.BOLD}Proposal Approved:{Colors.RESET} {res.get('message')}")
            if "coupled_workout" in res:
                print(f"• Downstream auto-booking: {res['coupled_workout']}")
            if "bumped_event" in res:
                bumped = res["bumped_event"]
                print(f"• Bumped Event: '{bumped['title']}' ({bumped['original_slot']}) marked BUMPED_BY_OVERRIDE.")
            if "reschedule_suggestion" in res:
                sugg = res["reschedule_suggestion"]
                print(f"• Assisted Rescheduling Recommendation to {sugg['recipient']}: {sugg['message']}")
            print()
            continue

        if user_input.strip() in ("[Reject]", "reject", "no", "cancel"):
            res = calendar_store.reject_pending_proposal()
            print(f"\n{Colors.YELLOW}{Colors.BOLD}Proposal Rejected:{Colors.RESET} {res.get('message')}\n")
            continue

        # Dispatch conversational query to ADK Multi-Agent Runner
        print(f"{Colors.CYAN}Processing with ADK multi-agent pipeline...{Colors.RESET}")
        try:
            response = run_turn(user_input, persona=current_persona)
            print(f"\n{Colors.BOLD}Response:{Colors.RESET}\n{response}\n")
        except Exception as e:
            print(f"\n{Colors.RED}Execution Error:{Colors.RESET} {e}\n")


if __name__ == "__main__":
    main()
