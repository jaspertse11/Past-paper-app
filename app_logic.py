"""Core session logic for the past-paper study app.

This file owns the actual state transitions of a question session: start, pause,
resume, finish, and save progress. It also determines the next question after a
question is complete and loads the relevant metadata from the JSON store.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from storage import QuestionStore


@dataclass
class QuestionSession:
    question_key: str
    question_pdf: Path
    solution_pdf: Optional[Path] = None
    started: bool = False
    finished: bool = False
    is_paused: bool = False
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    elapsed_before_pause: float = 0.0
    q_topic: str = ""
    remarks: str = ""

    @property
    def current_elapsed_seconds(self) -> float:
        if not self.started_at:
            return self.elapsed_before_pause

        if self.is_paused:
            return self.elapsed_before_pause

        return self.elapsed_before_pause + (datetime.now() - self.started_at).total_seconds()

    def start(self) -> None:
        if self.started and not self.is_paused:
            return

        if self.started_at is None:
            self.started_at = datetime.now()
        elif self.is_paused and self.paused_at is not None:
            self.started_at = datetime.now()
            self.paused_at = None

        self.started = True
        self.finished = False
        self.is_paused = False

    def pause(self) -> None:
        if not self.started or self.is_paused:
            return

        if self.started_at is not None:
            self.elapsed_before_pause += (datetime.now() - self.started_at).total_seconds()
            self.paused_at = datetime.now()
        self.is_paused = True

    def resume(self) -> None:
        if not self.started:
            self.start()
            return

        if self.is_paused:
            self.started_at = datetime.now()
            self.paused_at = None
            self.is_paused = False

    def finish(self) -> None:
        if self.started_at is not None and not self.is_paused:
            self.elapsed_before_pause += (datetime.now() - self.started_at).total_seconds()

        self.started = False
        self.finished = True
        self.is_paused = False
        self.paused_at = None
        self.started_at = None

    def reset(self) -> None:
        self.started = False
        self.finished = False
        self.is_paused = False
        self.started_at = None
        self.paused_at = None
        self.elapsed_before_pause = 0.0
        self.q_topic = ""
        self.remarks = ""


class PastPaperApp:
    @staticmethod
    def _normalize_filter_value(value):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned == "" or cleaned.lower() == "all":
                return None
            return cleaned
        return value

    @staticmethod
    def _normalize_completed_value(value):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in {"", "all"}:
                return None
            if cleaned in {"completed", "true", "yes", "1"}:
                return True
            if cleaned in {"incomplete", "false", "no", "0"}:
                return False
            return value
        return value

    def __init__(self, question_dir: str | Path = "QP_split", store_path: str | Path = "questions.json"):
        self.project_root = Path(__file__).resolve().parent

        def resolve_path(path_value: str | Path) -> Path:
            path = Path(path_value)
            if path.is_absolute():
                return path
            return (self.project_root / path).resolve()

        self.question_dir = resolve_path(question_dir)
        self.store = QuestionStore(resolve_path(store_path))
        self.store.sync_from_directory(self.question_dir)
        self.current_session: Optional[QuestionSession] = None
        self.active_pool_filters = {
            "paper": None,
            "topic": None,
            "q_type": None,
            "completed": None,
        }
        self._restore_incomplete_session()
        if self.current_session is None:
            self.current_session = self._make_dummy_session()

    def set_active_pool_filters(
        self,
        *,
        paper: Optional[str] = None,
        topic: Optional[str] = None,
        q_type: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> None:
        self.active_pool_filters = {
            "paper": self._normalize_filter_value(paper),
            "topic": self._normalize_filter_value(topic),
            "q_type": self._normalize_filter_value(q_type),
            "completed": self._normalize_completed_value(completed),
        }

    def _restore_incomplete_session(self):
        incomplete_key = self.store.get_incomplete_question()
        if not incomplete_key:
            return

        try:
            self.open_question(incomplete_key)
        except FileNotFoundError:
            pass

    def _make_dummy_session(self):
        dummy_key = "dummy_question_1P1_3_short.pdf"
        dummy_path = self.question_dir / dummy_key
        self.store.ensure_question_record(dummy_key)
        session = QuestionSession(
            question_key=dummy_key,
            question_pdf=dummy_path,
            solution_pdf=None,
        )
        self.current_session = session
        return session

    def list_question_keys(self) -> list[str]:
        return sorted(p.name for p in self.question_dir.glob("*.pdf"))

    def _parse_question_metadata(self, question_key: str) -> dict:
        name = question_key.replace(".pdf", "")
        parts = name.split("_")

        paper = None
        year = None

        for part in parts:
            if part.startswith("1P"):
                paper = part
            elif part.isdigit() and len(part) == 4:
                year = part

        return {
            "paper": paper,
            "year": year,
        }

    def find_solution_pdf(self, question_key: str) -> Optional[Path]:
        if not question_key.endswith(".pdf"):
            question_key = f"{question_key}.pdf"

        metadata = self._parse_question_metadata(question_key)
        paper = metadata.get("paper")
        year = metadata.get("year")

        if not paper or not year:
            return None

        candidate = self.project_root / paper / "CRIB" / f"CRIB_{year}.pdf"
        if candidate.exists():
            return candidate

        return None

    def open_question(self, question_key: str, solution_pdf: str | Path | None = None) -> QuestionSession:
        if not question_key.endswith(".pdf"):
            question_key = f"{question_key}.pdf"

        if self.current_session is not None and not self.current_session.finished:
            raise ValueError(f"A question is already open: {self.current_session.question_key}")

        q_path = self.question_dir / question_key
        if not q_path.exists() and not question_key.startswith("dummy_"):
            raise FileNotFoundError(f"Question PDF not found: {q_path}")

        self.store.ensure_question_record(question_key)
        record = self.store.get_question(question_key)

        resolved_solution = Path(solution_pdf) if solution_pdf is not None else None
        restored_elapsed = float(record.elapsed_seconds) if record else 0.0

        # An incomplete question should restore its elapsed time but remain paused
        # until the user explicitly clicks the timer. Auto-starting here causes the
        # timer to run as soon as the next question is opened.
        session = QuestionSession(
            question_key=question_key,
            question_pdf=q_path,
            solution_pdf=resolved_solution,
            elapsed_before_pause=restored_elapsed,
            started=False,
            is_paused=False,
            started_at=None,
        )
        self.current_session = session
        return session

    def start_timer(self) -> None:
        if self.current_session is None:
            raise ValueError("No question is open")
        self.current_session.start()

    def pause_timer(self) -> None:
        if self.current_session is None:
            raise ValueError("No question is open")
        self.current_session.pause()

    def resume_timer(self) -> None:
        if self.current_session is None:
            raise ValueError("No question is open")
        self.current_session.resume()

    def finish_question(self) -> None:
        if self.current_session is None:
            raise ValueError("No question is open")

        session = self.current_session
        if session.solution_pdf is None:
            session.solution_pdf = self.find_solution_pdf(session.question_key)

        session.finish()

    def save_session_progress(self) -> None:
        if self.current_session is None:
            return

        session = self.current_session
        record = self.store.get_question(session.question_key)
        if record is None:
            record = self.store.ensure_question_record(session.question_key)

        # Persist the current elapsed time even if the user closes the window mid-question.
        record.elapsed_seconds = round(session.current_elapsed_seconds, 2)
        record.is_completed = False
        self.store._save()

    def submit_attempt(
        self,
        score_percent: float,
        remarks: str,
        topic: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> dict:
        if self.current_session is None:
            raise ValueError("No question is open")

        session = self.current_session

        if not session.finished:
            session.finish()

        elapsed_seconds = round(session.current_elapsed_seconds, 2)

        record = self.store.get_question(session.question_key)
        next_attempt_no = 1 if record is None else len(record.attempts) + 1

        if record is not None:
            cleaned_topic = self.store.register_topic(topic)
            record.topic = cleaned_topic
            self.store._save()

        self.store.add_attempt(
            key=session.question_key,
            attempt_no=next_attempt_no,
            score_percent=float(score_percent),
            time_taken_sec=elapsed_seconds,
            remarks=remarks,
            timestamp=timestamp,
        )

        question_record = self.store.get_question(session.question_key)
        if question_record is not None:
            question_record.is_completed = True
            question_record.elapsed_seconds = 0.0
            if topic is not None:
                question_record.topic = self.store.register_topic(topic)
            self.store._save()

        # This is the correct place to define the “next question” algorithm.
        # After an attempt has been saved, the app decides which question should be
        # opened next based on completion state, ordering, and any selection rule.
        next_key = self.choose_next_question()
        if next_key is not None:
            self.current_session = self.open_question(next_key)
        else:
            self.current_session = None

        return {
            "question": session.question_key,
            "attempt_no": next_attempt_no,
            "score_percent": score_percent,
            "time_taken_sec": elapsed_seconds,
            "remarks": remarks,
            "record": question_record,
            "next_question": self.current_session.question_key if self.current_session is not None else None,
        }

    def get_question_pool(
        self,
        paper: Optional[str] = None,
        topic: Optional[str] = None,
        q_type: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> list[str]:
        paper = self._normalize_filter_value(paper)
        topic = self._normalize_filter_value(topic)
        q_type = self._normalize_filter_value(q_type)
        completed = self._normalize_completed_value(completed)

        keys = self.list_question_keys()
        pool = []

        for key in keys:
            record = self.store.get_question(key)
            if record is None:
                record = self.store.ensure_question_record(key)

            if paper and record.paper != paper:
                continue
            if topic and record.topic != topic:
                continue
            if q_type and record.q_type.lower() != q_type.lower():
                continue
            if completed is not None and record.is_completed != completed:
                continue

            # Default pool behaviour is the full question pool (both completed and
            # incomplete) unless the user explicitly asks for only completed or only
            # incomplete items.
            if completed is False and record.is_completed:
                continue

            pool.append(key)

        return sorted(pool)

    def choose_next_question(
        self,
        paper: Optional[str] = None,
        topic: Optional[str] = None,
        q_type: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> Optional[str]:
        # Algorithm hook: this method decides which question appears next.
        # If no explicit filter is provided, use the saved pool selection so the
        # selector and next-question logic stay in sync.
        if paper is None and topic is None and q_type is None and completed is None:
            paper = self.active_pool_filters.get("paper")
            topic = self.active_pool_filters.get("topic")
            q_type = self.active_pool_filters.get("q_type")
            completed = self.active_pool_filters.get("completed", False)

        pool = self.get_question_pool(
            paper=paper,
            topic=topic,
            q_type=q_type,
            completed=completed,
        )
        if not pool:
            return None
        return random.choice(pool)

    def next_question(self) -> QuestionSession:
        next_key = self.choose_next_question()
        if next_key is None:
            raise FileNotFoundError("No unattempted question available.")

        self.current_session = None
        return self.open_question(next_key)


if __name__ == "__main__":
    app = PastPaperApp(question_dir="QP_split")

    dummy_key = "dummy_question_1P1_3_short.pdf"
    dummy_session = QuestionSession(
        question_key=dummy_key,
        question_pdf=Path("QP_split") / dummy_key,
        solution_pdf=app.find_solution_pdf(dummy_key),
        started=True,
    )
    app.current_session = dummy_session

    app.start_timer()
    app.pause_timer()
    app.resume_timer()
    app.finish_question()

    result = app.submit_attempt(
        score_percent=83.5,
        q_topic="dummy_topic",
        remarks="dummy remark",
    )

    print(result)
    print(f"Next suggested question: {app.choose_next_question()}")
