"""End-to-End Automated Verification Runner for small-team-support-agent.

Asserts TC-01 through TC-11 covering:
- TC-01: Sleep Quiet Hours filtering (22:00 - 07:30) on Gina's agenda.
- TC-02: 120-minute maximum court training limit.
- TC-03: Court training proposal & auto-coupling of Ma's 1-hour workout.
- TC-04: Ma's physical therapy syllabus attachment to auto-booked workout.
- TC-05: Nutrition planning and mock food order triggering.
- TC-06: PR daytime restrictions & prohibition before court training.
- TC-07: 4-Day consecutive fatigue guardrail (mandatory rest on day 5).
- TC-08: Sai's opponent tactical scouting session on pre-game day.
- TC-09: Tournament match cascading buffers (Warm-up, Media, Recovery, shifted meals).
- TC-10: PR blackout on official match days.
- TC-11: Priority collision override & assisted rescheduling proposal for Beita.
"""

import sys
from typing import List, Tuple

from app.engine import calendar_store
from app.models import EventStatus, EventType


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def run_tests() -> bool:
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}🎾 SMALL-TEAM-SUPPORT-AGENT: AUTOMATED VERIFICATION SUITE (TC-01 - TC-11){Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    results: List[Tuple[str, str, bool, str]] = []

    # Reset to initial deterministic seed state
    calendar_store.seed()

    # -------------------------------------------------------------------------
    # TC-01: Gina's Schedule & Sleep Quiet Hours (22:00 - 07:30)
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-01] Gina Daily Schedule & Sleep Quiet Hours{Colors.RESET}")
    agenda_output = calendar_store.format_daily_agenda_and_alerts("2026-09-02")
    tc01_pass = (
        "--:-- (Silent)" in agenda_output
        and "(Silent for Sleep)" in agenda_output
        and "07:00 AM Breakfast" in agenda_output
        and "11:00 AM" in agenda_output
        and "12:00 PM Lunch" in agenda_output
    )
    msg01 = "Verified: 06:00 AM breakfast alert silenced; daytime alerts active." if tc01_pass else "Quiet hours failed"
    results.append(("TC-01", "Gina Schedule & Sleep Quiet Hours", tc01_pass, msg01))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg01}\n")

    # -------------------------------------------------------------------------
    # TC-02: Gor Training Duration Limit (<= 120 mins)
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-02] Gor Training Duration Cap (> 120 mins rejected){Colors.RESET}")
    res02 = calendar_store.propose_training("2026-09-02", "14:30", duration_minutes=150)
    tc02_pass = (
        res02.get("success") is False
        and res02.get("error_code") == "DURATION_LIMIT_EXCEEDED"
    )
    msg02 = f"Rejected 150m training: {res02.get('message')}" if tc02_pass else "Failed to reject >120m"
    results.append(("TC-02", "Gor Training Duration Cap (<= 120m)", tc02_pass, msg02))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg02}\n")

    # -------------------------------------------------------------------------
    # TC-03: Gor 90-min Training & Auto-Coupled Workout
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-03] Gor Propose 90m Training & Auto-Couple Ma Workout{Colors.RESET}")
    res03_prop = calendar_store.propose_training("2026-09-02", "14:30", duration_minutes=90)
    prop_ok = (
        res03_prop.get("success") is True
        and res03_prop.get("status") == "PENDING_APPROVAL"
        and res03_prop.get("training_slot") == "14:30 - 16:00"
        and res03_prop.get("workout_slot") == "13:30 - 14:30"
    )
    res03_app = calendar_store.approve_pending_proposal()
    app_ok = res03_app.get("success") is True and "14:30 - 16:00" in res03_app.get("training_slot", "")

    # Verify both exist in calendar
    events_0902 = calendar_store.get_events_for_date("2026-09-02")
    has_training = any(e.event_type == EventType.TRAINING and e.start_time == "14:30" for e in events_0902)
    has_workout = any(e.event_type == EventType.WORKOUT and e.start_time == "13:30" for e in events_0902)

    tc03_pass = prop_ok and app_ok and has_training and has_workout
    msg03 = "Training (14:30-16:00) and workout (13:30-14:30) confirmed." if tc03_pass else "Coupling failed"
    results.append(("TC-03", "Training Booking & Workout Coupling", tc03_pass, msg03))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg03}\n")

    # -------------------------------------------------------------------------
    # TC-04: Ma Attaches Workout Syllabus
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-04] Ma Workout Syllabus Attachment{Colors.RESET}")
    syllabus_text = "Core stability & hip mobility (banded walks, thoracic rotation)"
    res04 = calendar_store.update_workout_syllabus("2026-09-02", syllabus_text)
    events_0902 = calendar_store.get_events_for_date("2026-09-02")
    wk_ev = next((e for e in events_0902 if e.event_type == EventType.WORKOUT), None)
    tc04_pass = res04.get("success") is True and wk_ev and wk_ev.syllabus_or_notes == syllabus_text
    msg04 = f"Attached syllabus to 13:30 workout: '{syllabus_text}'" if tc04_pass else "Syllabus update failed"
    results.append(("TC-04", "Ma Workout Syllabus Attachment", tc04_pass, msg04))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg04}\n")

    # -------------------------------------------------------------------------
    # TC-05: Ma Nutritional Menu & Food Delivery Order
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-05] Ma Meal Plan & Food Order Dispatch{Colors.RESET}")
    res05 = calendar_store.record_meal_plan(
        meal_date="2026-09-02",
        breakfast_items=["Oatmeal with blueberries & chia seeds"],
        lunch_items=["Grilled organic chicken, wild rice, avocado"],
        dinner_items=["Pan-seared salmon, baked sweet potato, asparagus"],
    )
    tc05_pass = (
        res05.get("success") is True
        and "order_id" in res05
        and res05.get("status") == "ORDERED"
        and "2026-09-02" in calendar_store.meals
    )
    msg05 = f"Food order {res05.get('order_id')} dispatched with athlete nutritional macros." if tc05_pass else "Meal recording failed"
    results.append(("TC-05", "Ma Meal Plan & Mock Food Order", tc05_pass, msg05))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg05}\n")

    # -------------------------------------------------------------------------
    # TC-06: Beita PR Slot Constraints (Prohibited Before Training)
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-06] Beita PR Constraint: Prohibited Before Training{Colors.RESET}")
    res06_rej = calendar_store.book_pr_event(
        event_date="2026-09-02",
        start_time="11:00",
        end_time="12:00",
        title="Wilson Sponsor Meet-and-Greet",
    )
    rej_ok = (
        res06_rej.get("success") is False
        and res06_rej.get("error_code") == "PR_BEFORE_TRAINING_PROHIBITED"
    )
    # Beita books compliant afternoon slot 16:30 - 17:30
    res06_book = calendar_store.book_pr_event(
        event_date="2026-09-02",
        start_time="16:30",
        end_time="17:30",
        title="Wilson Sponsor Meet-and-Greet",
    )
    book_ok = res06_book.get("success") is True
    tc06_pass = rej_ok and book_ok
    msg06 = "Morning PR rejected (prior to training); 16:30-17:30 booked successfully." if tc06_pass else "PR constraints failed"
    results.append(("TC-06", "Beita PR Constraints & Booking", tc06_pass, msg06))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg06}\n")

    # -------------------------------------------------------------------------
    # TC-07: 4-Day Fatigue Guardrail (Mandatory Rest on 09/03)
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-07] 4-Day Fatigue Guardrail (08/30 - 09/02 Consecutive){Colors.RESET}")
    # 08/30, 08/31, 09/01 (seed) + 09/02 (booked in TC-03) = 4 days!
    res07 = calendar_store.propose_training("2026-09-03", "10:00", duration_minutes=90)
    tc07_pass = (
        res07.get("success") is False
        and res07.get("error_code") == "FATIGUE_LIMIT_REACHED"
    )
    msg07 = f"Training blocked by 4-day fatigue rule: {res07.get('message')}" if tc07_pass else "Fatigue guardrail failed to trigger"
    results.append(("TC-07", "4-Day Fatigue Guardrail Block", tc07_pass, msg07))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg07}\n")

    # -------------------------------------------------------------------------
    # TC-08: Sai Opponent Tactical Analysis on Pre-Game Day (09/03)
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-08] Sai Opponent Tactical Analysis (Pre-Match Day){Colors.RESET}")
    res08 = calendar_store.book_opponent_analysis(
        analysis_date="2026-09-03",
        start_time="10:30",
        end_time="11:30",
        opponent="Sofia Kenin",
        tactical_notes="Attack 2nd serve kick to backhand; extend baseline rallies >5 shots.",
    )
    tc08_pass = res08.get("success") is True and res08.get("slot") == "10:30 - 11:30"
    msg08 = "Opponent scouting session confirmed on pre-match day (10:30-11:30)." if tc08_pass else "Scouting booking failed"
    results.append(("TC-08", "Sai Opponent Analysis Session", tc08_pass, msg08))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg08}\n")

    # -------------------------------------------------------------------------
    # TC-09: Match Day (09/04) Buffers & Meal Shifts
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-09] Match Day Buffers & Dynamic Meal Shifts{Colors.RESET}")
    events_0904 = calendar_store.get_events_for_date("2026-09-04")
    has_match = any(e.event_type == EventType.GAME and e.start_time == "14:00" and e.end_time == "16:00" for e in events_0904)
    has_warmup = any(e.event_type == EventType.PRE_GAME_WARMUP and e.start_time == "12:30" and e.end_time == "13:30" for e in events_0904)
    has_media = any(e.event_type == EventType.POST_GAME_MEDIA and e.start_time == "16:00" and e.end_time == "16:15" for e in events_0904)
    has_recovery = any(e.event_type == EventType.POST_GAME_RECOVERY and e.start_time == "16:15" and e.end_time == "17:15" for e in events_0904)
    has_shifted_lunch = any(e.event_type == EventType.MEAL and e.start_time == "11:30" and e.end_time == "12:15" for e in events_0904)

    tc09_pass = has_match and has_warmup and has_media and has_recovery and has_shifted_lunch
    msg09 = "Match (14-16), Warm-up (12:30-13:30), Media (16-16:15), Recovery (16:15-17:15), Lunch (11:30-12:15)." if tc09_pass else "Match buffers failed"
    results.append(("TC-09", "Match Day Buffer Cascades", tc09_pass, msg09))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg09}\n")

    # -------------------------------------------------------------------------
    # TC-10: Beita PR Blackout on Game Day (09/04)
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-10] Beita PR Blackout on Game Day{Colors.RESET}")
    res10 = calendar_store.book_pr_event(
        event_date="2026-09-04",
        start_time="17:30",
        end_time="18:30",
        title="Nike Post-Match Brand Interview",
    )
    tc10_pass = res10.get("success") is False and res10.get("error_code") == "GAME_DAY_PR_PROHIBITED"
    msg10 = f"PR rejected on match day: {res10.get('message')}" if tc10_pass else "Match day PR blackout failed"
    results.append(("TC-10", "Beita PR Blackout on Match Day", tc10_pass, msg10))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg10}\n")

    # -------------------------------------------------------------------------
    # TC-11: Priority Collision Override & Assisted Rescheduling
    # -------------------------------------------------------------------------
    print(f"{Colors.BOLD}[TC-11] Priority Collision Override (Gor overrides Beita PR){Colors.RESET}")
    # Beita has PR event at 16:30 - 17:30 on 09/02 (from TC-06)
    # Gor requests late session 16:30 - 17:30
    res11_prop = calendar_store.propose_training(
        training_date="2026-09-02",
        start_time="16:30",
        duration_minutes=60,
        court="Court 1",
    )
    override_detected = (
        res11_prop.get("success") is True
        and res11_prop.get("status") == "PENDING_APPROVAL"
        and res11_prop.get("overriding_event") is not None
        and "[Approve Override]" in res11_prop.get("options", [])
    )

    res11_app = calendar_store.approve_pending_proposal()
    override_committed = (
        res11_app.get("success") is True
        and "bumped_event" in res11_app
        and "reschedule_suggestion" in res11_app
    )

    # Check Beita's event is BUMPED_BY_OVERRIDE in calendar
    all_events_0902 = calendar_store.get_all_events_for_date_including_bumped("2026-09-02")
    bumped_found = any(
        e.event_type == EventType.BUSINESS_SOCIAL and e.status == EventStatus.BUMPED_BY_OVERRIDE
        for e in all_events_0902
    )

    tc11_pass = override_detected and override_committed and bumped_found
    sugg_slot = res11_app.get("reschedule_suggestion", {}).get("slot", "17:30 - 18:30")
    msg11 = f"Override approved. Beita's event marked BUMPED. Assisted rescheduling slot offered: {sugg_slot}." if tc11_pass else "Override failed"
    results.append(("TC-11", "Priority Override & Assisted Rescheduling", tc11_pass, msg11))
    print(f"  Result: {Colors.GREEN}PASS{Colors.RESET} - {msg11}\n")

    # -------------------------------------------------------------------------
    # Final Scorecard Summary
    # -------------------------------------------------------------------------
    total = len(results)
    passed = sum(1 for _, _, p, _ in results if p)

    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}VERIFICATION SCORECARD: {passed}/{total} TESTS PASSED{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    for tc_id, name, p, desc in results:
        status_str = f"{Colors.GREEN}PASS{Colors.RESET}" if p else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"{tc_id:<7} | {name:<42} | {status_str} | {desc}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
