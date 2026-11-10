"""Employee permission catalogue.

Admins implicitly hold every permission. Employees hold only the permissions an admin
granted when approving them (or later edited). The catalogue is synced into the
`permissions` table by `python -m app.cli bootstrap`; later phases add codes here.
"""

PERMISSIONS: list[tuple[str, str, str]] = [
    # (code, description, category)
    ("manage_categories", "Create and edit recruitment categories", "Recruitment"),
    ("manage_job_openings", "Create, edit, publish and close job openings", "Recruitment"),
    ("review_applications", "Review applications and approve or reject them", "Recruitment"),
    ("analyze_resumes", "Run AI resume analysis and correct extracted data", "Resumes"),
    ("bulk_upload_resumes", "Upload and process resumes in bulk", "Resumes"),
    ("manage_question_bank", "Maintain the reusable aptitude question bank", "Assessments"),
    ("generate_assessments", "Generate assessment questions with AI", "Assessments"),
    ("approve_assessments", "Review, edit and approve assessments", "Assessments"),
    ("schedule_tests", "Schedule tests, send invitations and handle reschedule requests", "Assessments"),
    ("review_results", "Review evaluations, override scores, shortlist or reject", "Evaluation"),
    ("manage_interviews", "Schedule interviews and record feedback", "Interviews"),
    ("view_analytics", "View recruitment analytics and export reports", "Analytics"),
]

PERMISSION_CODES = {code for code, _, _ in PERMISSIONS}
