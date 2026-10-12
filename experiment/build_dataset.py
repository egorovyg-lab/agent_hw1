"""Create a reproducible 100-tool pool and 30 labeled selection queries."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "data"
OUT.mkdir(parents=True, exist_ok=True)
CORE = [
    ("schedule_search", "Search lesson schedule by text across lesson title, course, teacher, room, and optional date. Use when the user asks what class matches a topic, room, or name; do not use for a known event ID or room availability."),
    ("schedule_get", "Retrieve one lesson by exact event ID, including date, time, title, room, teacher, course, building, and source. Use after an ID is known; do not use for a free-text search."),
    ("schedule_by_teacher", "Find lessons by teacher name and optional date. Use when the user asks when or what a teacher teaches; do not use to search a room or course title."),
    ("schedule_room_availability", "Check whether a room is free for a date, start time, and duration. Use for a time interval availability question; do not use to list all room classes."),
]
NEAR = [
    ("schedule_course_search", "Search course catalog descriptions by course title and subject; returns course metadata, not individual lesson times."),
    ("schedule_room_list", "List all lessons assigned to a room over a date range; use for room history rather than checking a free interval."),
    ("schedule_teacher_profile", "Return a teacher's office, contact details, and biography; does not show their lessons."),
    ("schedule_event_create", "Create a new calendar event from a title and time; modifies a personal calendar, not the class schedule."),
    ("schedule_event_cancel", "Cancel a personal calendar event by event ID; does not search or read course records."),
    ("schedule_exam_search", "Search exam dates and locations by subject; excludes ordinary lessons and seminars."),
    ("schedule_deadline_search", "Find assignment due dates by course; does not return class meeting times."),
    ("schedule_building_map", "Find a building and room on a campus map; does not report whether the room is occupied."),
    ("schedule_room_capacity", "Return the seating capacity and equipment of a room; does not check its schedule."),
    ("schedule_teacher_hours", "Find teacher office hours by teacher name; do not use for teaching timetable."),
    ("schedule_student_calendar", "List a student's enrolled classes using student ID; differs from querying the global timetable."),
    ("schedule_group_calendar", "List meetings for a study group; does not return official lessons."),
    ("schedule_time_convert", "Convert a time between time zones; does not search lesson records."),
    ("schedule_date_week", "Return the week number and weekday for a date; no schedule lookup."),
    ("schedule_conflict_check", "Compare two supplied events for overlap; does not search for the schedule itself."),
    ("schedule_substitute_teacher", "Find the substitute assigned to a class; does not list the teacher's full timetable."),
    ("schedule_attendance", "Read attendance for a class event ID; does not return event details or availability."),
    ("schedule_room_reserve", "Reserve a room for a requested interval; this changes state and is not a read-only availability check."),
    ("schedule_notice_search", "Search announcements about timetable changes; does not return the base timetable."),
    ("schedule_export_ical", "Export a calendar in iCalendar format for a known user; does not answer a schedule question."),
    ("schedule_course_roster", "List students enrolled in a course; no meeting dates or room information."),
    ("schedule_semester_dates", "Return semester start, end, and holidays; does not locate a class meeting."),
    ("schedule_room_equipment", "Return available equipment in a classroom; no occupancy or lesson records."),
    ("schedule_change_request", "Submit a request to change a class time or room; this creates a request rather than searching."),
]
OTHER = {
    "weather": ["weather_current", "weather_forecast", "weather_alerts", "weather_history", "weather_air_quality", "weather_uv_index", "weather_sunrise_sunset", "weather_rain_probability", "weather_wind", "weather_location_lookup", "weather_hourly", "weather_compare"],
    "email": ["email_search", "email_get", "email_send", "email_draft", "email_archive", "email_label", "email_attachment_list", "email_unread_count", "email_thread_reply", "email_spam_report", "email_contact_lookup", "email_delete"],
    "expenses": ["expense_search", "expense_create", "expense_receipt_read", "expense_category_summary", "expense_budget_check", "expense_reimburse", "expense_vendor_lookup", "expense_monthly_report", "expense_currency_convert", "expense_policy_search", "expense_export", "expense_approve"],
    "files": ["file_search", "file_get", "file_upload", "file_share", "file_permissions", "file_move", "file_version_list", "file_delete", "file_tag", "file_summarize", "file_duplicate_check", "file_folder_list"],
    "travel": ["travel_flight_search", "travel_hotel_search", "travel_itinerary_get", "travel_booking_cancel", "travel_checkin", "travel_price_alert", "travel_route_plan", "travel_train_search", "travel_car_rental", "travel_policy_lookup", "travel_expense_estimate", "travel_booking_create"],
    "tasks": ["task_search", "task_create", "task_update", "task_due_soon", "task_assign", "task_complete", "task_board_summary", "task_dependency_check", "task_comment_add", "task_priority_set", "task_project_list", "task_delete"],
}
OTHER_DESC = {
    "weather": "Query weather conditions, forecasts, alerts, or atmospheric measurements for a location and time.",
    "email": "Search, read, compose, send, organize, or manage email messages and contacts.",
    "expenses": "Search, record, classify, approve, reimburse, or report business expenses and receipts.",
    "files": "Search, read, upload, share, organize, summarize, or manage files and folders.",
    "travel": "Search, compare, retrieve, or manage flights, hotels, ground transport, and travel plans.",
    "tasks": "Search, create, update, assign, complete, or report project tasks and due dates.",
}
QUERIES = [
    ("q01", "What class is in room 204 on October 12?", "schedule_search"), ("q02", "Find the lesson about MCP on October 15.", "schedule_search"),
    ("q03", "Search the timetable for the agents course.", "schedule_search"), ("q04", "Which class is taught by A. Ivanova in room 204?", "schedule_search"),
    ("q05", "Look up the seminar about tools on October 13.", "schedule_search"), ("q06", "Find classes in the Main Building that mention agents.", "schedule_search"),
    ("q07", "Show the lesson matching the room number 314.", "schedule_search"),
    ("q08", "Retrieve the full record for event class-001.", "schedule_get"), ("q09", "What are all fields and source details for class-003?", "schedule_get"),
    ("q10", "Get the lesson whose event ID is class-002.", "schedule_get"), ("q11", "Open event class-001 and show its teacher and building.", "schedule_get"),
    ("q12", "Fetch the exact schedule record for class-003.", "schedule_get"), ("q13", "Return the detailed entry identified by class-002.", "schedule_get"),
    ("q14", "I have ID class-001; retrieve that event.", "schedule_get"),
    ("q15", "When does A. Ivanova teach?", "schedule_by_teacher"), ("q16", "Find all lessons for I. Petrov.", "schedule_by_teacher"),
    ("q17", "Show classes taught by Ivanova on October 15.", "schedule_by_teacher"), ("q18", "Which dates have a lesson with Petrov?", "schedule_by_teacher"),
    ("q19", "Look up the timetable for teacher A. Ivanova.", "schedule_by_teacher"), ("q20", "Find what I. Petrov teaches on October 13.", "schedule_by_teacher"),
    ("q21", "List sessions led by Ivanova, regardless of room.", "schedule_by_teacher"),
    ("q22", "Is room 204 free from 18:15 for thirty minutes on October 12?", "schedule_room_availability"),
    ("q23", "Check if classroom 314 is available at 18:00 on October 13 for 45 minutes.", "schedule_room_availability"),
    ("q24", "Can I use room 204 at 20:00 on October 15 for one hour?", "schedule_room_availability"),
    ("q25", "Check availability for room 101 on October 12, 16:00-17:00.", "schedule_room_availability"),
    ("q26", "Will room 204 be occupied at 18:30 on October 12 for 20 minutes?", "schedule_room_availability"),
    ("q27", "Is classroom 314 vacant from 20:00 for half an hour on October 13?", "schedule_room_availability"),
    ("q28", "Test whether room 204 is free at 17:00 on October 15 for 30 minutes.", "schedule_room_availability"),
    ("q29", "Can a meeting use room 204 at 19:00 on October 12 for 15 minutes?", "schedule_room_availability"),
    ("q30", "Check the room's occupancy for October 13 at 18:15, duration 30 minutes, room 314.", "schedule_room_availability"),
]
tools = [{"name": n, "description": d, "kind": "gold"} for n, d in CORE]
tools += [{"name": n, "description": d, "kind": "near_distractor"} for n, d in NEAR]
for category, names in OTHER.items():
    for name in names:
        tools.append({"name": name, "description": f"{OTHER_DESC[category]} This operation is `{name}`.", "kind": "distractor"})
assert len(tools) == 100 and len({x["name"] for x in tools}) == 100 and len(QUERIES) == 30 and len(NEAR) >= 20
(OUT / "tools.json").write_text(json.dumps(tools, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "queries.json").write_text(json.dumps([{"id": i, "query": q, "gold_tool": g} for i, q, g in QUERIES], ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {len(tools)} tools ({len(NEAR)} near distractors) and {len(QUERIES)} queries")
