"""JSON storage layer for the past-paper app.

This file is responsible for reading and writing the question progress file,
tracking all attempts, and inferring metadata such as paper number, question
number, and question type from the PDF filename.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Attempt:
    attempt_no: int
    score_percent: float
    time_taken_sec: float
    remarks: str
    time: str


@dataclass
class QuestionRecord:
    paper: str
    q_num: int
    q_type: str
    is_completed: bool = False
    elapsed_seconds: float = 0.0
    topic: Optional[str] = None
    attempts: List[Attempt] = field(default_factory=list)


class QuestionStore:
    def __init__(self, file_path: str | Path = "questions.json"):
        base_dir = Path(__file__).resolve().parent
        path = Path(file_path)
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        self.file_path = path
        self.questions: Dict[str, QuestionRecord] = {}
        self.topics: set[str] = set()
        self._load()

    def _parse_question_key(self, key: str):
        # Example: QP_2015_1P1_3_short.pdf
        # or: QP_2015_1P1_3_short
        # We strip the .pdf extension if present.
        key = key.replace(".pdf", "")
        parts = key.split("_")

        if len(parts) < 4:
            raise ValueError(f"Invalid question key format: {key}")

        # The last part is q_type, e.g. short/long
        q_type = parts[-1].lower()
        q_num = int(parts[-1]) if parts[-1].isdigit() else None

        # If the filename is something like QP_2015_1P1_3_short,
        # the question number is the second-to-last segment before q_type.
        if q_num is None:
            q_num = int(parts[-2])

        # The paper is the segment immediately before q_num.
        paper = parts[-2] if q_num is not None and parts[-2].startswith("1P") else parts[-3]
        if not paper.startswith("1P"):
            paper = parts[-3]

        return {
            "paper": paper,
            "q_num": int(q_num),
            "q_type": q_type,
        }

    def _infer_from_key(self, key: str):
        normalized = key.replace(".pdf", "")
        parts = normalized.split("_")

        if len(parts) < 4:
            raise ValueError(f"Question filename/key does not contain enough info: {key}")

        q_type = parts[-1].lower()
        if q_type not in {"short", "long"}:
            raise ValueError(f"Unknown question type in key: {key}")

        q_num = int(parts[-2])
        paper = parts[-3]

        if not paper.startswith("1P"):
            raise ValueError(f"Invalid paper label in key: {key}")

        return {
            "paper": paper,
            "q_num": q_num,
            "q_type": q_type,
        }

    def _load(self):
        if not self.file_path.exists():
            self.questions = {}
            return

        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                raw_text = f.read().strip()
            if not raw_text:
                self.questions = {}
                return
            raw = json.loads(raw_text)
        except (json.JSONDecodeError, OSError):
            self.questions = {}
            return

        if not isinstance(raw, dict):
            self.questions = {}
            return

        for key, value in raw.items():
            parsed = self._infer_from_key(key)
            record = QuestionRecord(
                paper=parsed["paper"],
                q_num=parsed["q_num"],
                q_type=parsed["q_type"],
                is_completed=value.get("is_completed", False),
                elapsed_seconds=float(value.get("elapsed_seconds", 0.0)),
                topic=value.get("topic"),
                attempts=[
                    Attempt(
                        attempt_no=a["attempt_no"],
                        score_percent=a["score_percent"],
                        time_taken_sec=a["time_taken_sec"],
                        remarks=a["remarks"],
                        time=a["time"],
                    )
                    for a in value.get("attempts", [])
                ],
            )
            self.questions[key] = record

        self._refresh_topics()

    def _refresh_topics(self):
        self.topics = set()
        for question in self.questions.values():
            if question.topic:
                self.topics.add(question.topic)

    def sync_from_directory(self, directory: str | Path):
        folder = Path(directory)
        if not folder.exists():
            return

        valid_keys = set()
        for pdf_path in sorted(folder.glob("*.pdf")):
            key = pdf_path.name
            valid_keys.add(key)
            self.ensure_question_record(key)

        stale_keys = [key for key in list(self.questions.keys()) if key not in valid_keys]
        for key in stale_keys:
            del self.questions[key]

        self._save()

    def _save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for key, question in self.questions.items():
            data[key] = {
                "paper": question.paper,
                "q_num": question.q_num,
                "q_type": question.q_type,
                "is_completed": question.is_completed,
                "elapsed_seconds": round(float(question.elapsed_seconds), 2),
                "topic": question.topic,
                "attempts": [
                    {
                        "attempt_no": a.attempt_no,
                        "score_percent": a.score_percent,
                        "time_taken_sec": a.time_taken_sec,
                        "remarks": a.remarks,
                        "time": a.time,
                    }
                    for a in question.attempts
                ],
            }

        payload = json.dumps(data, indent=2)
        with self.file_path.open("w", encoding="utf-8") as f:
            f.write(payload)

        self._refresh_topics()

    def ensure_question_record(self, key: str):
        key = key if key.endswith(".pdf") else f"{key}.pdf"
        if key in self.questions:
            return self.questions[key]

        parsed = self._infer_from_key(key)
        record = QuestionRecord(
            paper=parsed["paper"],
            q_num=parsed["q_num"],
            q_type=parsed["q_type"],
            is_completed=False,
            topic=None,
        )
        self.questions[key] = record
        self._save()
        return record

    def register_topic(self, topic: Optional[str]) -> Optional[str]:
        if topic is None:
            return None

        cleaned = topic.strip()
        if not cleaned:
            return None

        self.topics.add(cleaned)
        return cleaned

    def get_all_topics(self, completed_only: bool = False) -> list[str]:
        self._refresh_topics()
        if not completed_only:
            return sorted(self.topics)

        topics = set()
        for question in self.questions.values():
            if question.is_completed and question.topic:
                topics.add(question.topic)
        return sorted(topics)

    def get_all_papers(self) -> list[str]:
        papers = {question.paper for question in self.questions.values()}
        return sorted(papers)

    def filter_questions(
        self,
        paper: Optional[str] = None,
        topic: Optional[str] = None,
        q_type: Optional[str] = None,
        completed: Optional[bool] = None,
    ):
        results = {}
        for key, question in self.questions.items():
            if paper and question.paper != paper:
                continue
            if topic and question.topic != topic:
                continue
            if q_type and question.q_type.lower() != q_type.lower():
                continue
            if completed is not None and question.is_completed != completed:
                continue
            results[key] = question
        return results

    def add_attempt(
        self,
        key: str,
        attempt_no: int,
        score_percent: float,
        time_taken_sec: float,
        remarks: str,
        timestamp: Optional[str] = None,
    ):
        key = key if key.endswith(".pdf") else f"{key}.pdf"
        parsed = self._infer_from_key(key)

        if key not in self.questions:
            self.questions[key] = QuestionRecord(
                paper=parsed["paper"],
                q_num=parsed["q_num"],
                q_type=parsed["q_type"],
            )

        question = self.questions[key]
        if timestamp is None:
            timestamp = datetime.now().isoformat(timespec="seconds")

        question.attempts.append(
            Attempt(
                attempt_no=attempt_no,
                score_percent=score_percent,
                time_taken_sec=time_taken_sec,
                remarks=remarks,
                time=timestamp,
            )
        )
        question.is_completed = True
        question.elapsed_seconds = 0.0

        self._save()

    def get_question(self, key: str):
        key = key if key.endswith(".pdf") else f"{key}.pdf"
        return self.questions.get(key)

    def get_incomplete_question(self):
        for key, question in self.questions.items():
            if not question.is_completed:
                return key
        return None

    def all_questions(self):
        return self.questions


if __name__ == "__main__":
    store = QuestionStore("questions.json")
    store.add_attempt(
        key="dummy_paper_1P1_3_short",
        attempt_no=1,
        score_percent=82.5,
        time_taken_sec=310,
        remarks="Example attempt",
    )
    store.add_attempt(
        key="dummy_paper_1P1_3_short",
        attempt_no=2,
        score_percent=91.0,
        time_taken_sec=250,
        remarks="Another example attempt",
    )

    print(json.dumps(store.all_questions(), default=str, indent=2))
