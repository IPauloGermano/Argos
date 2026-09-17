from app.services.change_detector import detect_job_changes, is_critical_update


class DummyJob:
    def __init__(self, salary_min=5000.0, salary_max=8000.0, work_mode="onsite", location="SP", description="Curta", status="active"):
        self.salary_min = salary_min
        self.salary_max = salary_max
        self.work_mode = work_mode
        self.location = location
        self.description = description
        self.status = status


def test_detect_salary_and_mode_changes():
    old = DummyJob(salary_min=5000.0, salary_max=8000.0, work_mode="onsite")
    new_data = {
        "salary_min": 7000.0,
        "salary_max": 10000.0,
        "work_mode": "remote",
        "location": "SP",
        "description": "Curta",
        "status": "active"
    }

    changes = detect_job_changes(old, new_data)
    assert len(changes) == 3  # min, max, work_mode
    types = {c["change_type"] for c in changes}
    assert "salary_update" in types
    assert "work_mode_update" in types
    assert is_critical_update(changes) is True


def test_no_changes():
    old = DummyJob()
    new_data = {
        "salary_min": 5000.0,
        "salary_max": 8000.0,
        "work_mode": "onsite",
        "location": "SP",
        "description": "Curta",
        "status": "active"
    }
    changes = detect_job_changes(old, new_data)
    assert len(changes) == 0
    assert is_critical_update(changes) is False
