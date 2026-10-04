"""Tkinter GUI for the past-paper workflow.

This file is the UI layer. It renders the selected question, the timer button,
and the finish flow. It does not contain the data logic itself; that lives in the
app_logic and storage modules.
"""

import os
import random
import tkinter as tk
from tkinter import messagebox

from app_logic import PastPaperApp


class QuestionSelectorDialog(tk.Toplevel):
    """Filter-driven question picker that uses the same pool logic as next-question routing."""

    def __init__(self, parent, app: PastPaperApp):
        super().__init__(parent)
        self.title("Question selector")
        self.geometry("520x420")
        self.transient(parent)
        self.grab_set()

        self.app = app
        self.selected_key = None

        paper_choices = ["All"] + sorted({self.app.store._infer_from_key(key)["paper"] for key in self.app.list_question_keys()})
        topic_choices = ["All"] + self.app.store.get_all_topics()

        def saved_display_value(field_name, fallback="All"):
            value = self.app.active_pool_filters.get(field_name)
            if value in (None, "All"):
                return fallback
            if field_name == "completed":
                if value is True:
                    return "Completed"
                if value is False:
                    return "Incomplete"
                return fallback
            return value

        filter_frame = tk.Frame(self)
        filter_frame.pack(fill="x", padx=12, pady=(12, 8))

        tk.Label(filter_frame, text="Paper:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.paper_var = tk.StringVar(value=saved_display_value("paper"))
        self.paper_menu = tk.OptionMenu(filter_frame, self.paper_var, *paper_choices, command=lambda *args: self.refresh_pool())
        self.paper_menu.grid(row=0, column=1, sticky="ew", padx=(0, 12))

        tk.Label(filter_frame, text="Topic:", font=("Arial", 10, "bold")).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.topic_var = tk.StringVar(value=saved_display_value("topic"))
        self.topic_menu = tk.OptionMenu(filter_frame, self.topic_var, *topic_choices, command=lambda *args: self.refresh_pool())
        self.topic_menu.grid(row=0, column=3, sticky="ew")

        tk.Label(filter_frame, text="Type:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.qtype_var = tk.StringVar(value=saved_display_value("q_type"))
        self.qtype_menu = tk.OptionMenu(filter_frame, self.qtype_var, "All", "short", "long", command=lambda *args: self.refresh_pool())
        self.qtype_menu.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(8, 0))

        tk.Label(filter_frame, text="Completed:", font=("Arial", 10, "bold")).grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(8, 0))
        self.completed_var = tk.StringVar(value=saved_display_value("completed"))
        self.completed_menu = tk.OptionMenu(filter_frame, self.completed_var, "All", "Completed", "Incomplete", command=lambda *args: self.refresh_pool())
        self.completed_menu.grid(row=1, column=3, sticky="ew", pady=(8, 0))

        filter_frame.columnconfigure(1, weight=1)
        filter_frame.columnconfigure(3, weight=1)

        button_row = tk.Frame(self)
        button_row.pack(fill="x", padx=12, pady=(0, 6))
        tk.Button(button_row, text="Select pool", command=self.select_pool).pack(side="left")
        self.pool_count_label = tk.Label(button_row, text="0 questions", font=("Arial", 10, "bold"))
        self.pool_count_label.pack(side="left", padx=(8, 0))

        self.pool_listbox = tk.Listbox(self, height=16, exportselection=False, font=("Arial", 10))
        self.pool_listbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.pool_listbox.bind("<<ListboxSelect>>", self._select_pool_item)
        self.pool_listbox.bind("<Double-Button-1>", lambda event: self._load_selected_question())

        self._refresh_filter_option_counts()
        self.refresh_pool()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _resolve_filter_value(self, var_value):
        if var_value is None:
            return None
        value = str(var_value).strip()
        if value in {"", "All"}:
            return None
        return value

    def _resolve_completed_flag(self):
        value = str(self.completed_var.get() or "").strip()
        if value in {"", "All"}:
            return None
        if value == "Completed":
            return True
        if value == "Incomplete":
            return False
        return None

    def _count_for_filter(self, *, paper=None, topic=None, q_type=None, completed=None):
        if paper in {None, "All"}:
            paper = None
        if topic in {None, "All"}:
            topic = None
        if q_type in {None, "All"}:
            q_type = None
        return len(self.app.get_question_pool(paper=paper, topic=topic, q_type=q_type, completed=completed))

    def _refresh_filter_option_counts(self):
        state = {
            "paper": self._resolve_filter_value(self.paper_var.get()),
            "topic": self._resolve_filter_value(self.topic_var.get()),
            "q_type": self._resolve_filter_value(self.qtype_var.get()),
            "completed": self._resolve_completed_flag(),
        }

        static_papers = ["All"] + sorted({self.app.store._infer_from_key(key)["paper"] for key in self.app.list_question_keys()})
        static_topics = ["All"] + self.app.store.get_all_topics()
        static_qtypes = ["All", "short", "long"]
        static_completed = ["All", "Completed", "Incomplete"]

        def set_option_menu(menu, items):
            menu_menu = menu["menu"]
            menu_menu.delete(0, "end")
            for raw_value, label in items:
                def command_factory(value, target_menu):
                    return lambda: self._apply_selected_menu_value(target_menu, value)
                menu_menu.add_command(label=label, command=command_factory(raw_value, menu))

        paper_items = []
        for paper in static_papers:
            count = self._count_for_filter(
                paper=paper,
                topic=state["topic"],
                q_type=state["q_type"],
                completed=state["completed"],
            )
            paper_items.append((paper, f"{paper} ({count})"))
        set_option_menu(self.paper_menu, paper_items)

        topic_items = []
        for topic in static_topics:
            count = self._count_for_filter(
                paper=state["paper"],
                topic=topic,
                q_type=state["q_type"],
                completed=state["completed"],
            )
            topic_items.append((topic, f"{topic} ({count})"))
        set_option_menu(self.topic_menu, topic_items)

        qtype_items = []
        for qtype in static_qtypes:
            count = self._count_for_filter(
                paper=state["paper"],
                topic=state["topic"],
                q_type=qtype,
                completed=state["completed"],
            )
            qtype_items.append((qtype, f"{qtype} ({count})"))
        set_option_menu(self.qtype_menu, qtype_items)

        completed_items = []
        for completed in static_completed:
            raw_value = {"All": None, "Completed": True, "Incomplete": False}[completed]
            count = self._count_for_filter(
                paper=state["paper"],
                topic=state["topic"],
                q_type=state["q_type"],
                completed=raw_value,
            )
            completed_items.append((raw_value, f"{completed} ({count})"))
        set_option_menu(self.completed_menu, completed_items)

        current_paper = self._resolve_filter_value(self.paper_var.get())
        self.paper_var.set("All" if current_paper is None else current_paper)

        current_topic = self._resolve_filter_value(self.topic_var.get())
        self.topic_var.set("All" if current_topic is None else current_topic)

        current_qtype = self._resolve_filter_value(self.qtype_var.get())
        self.qtype_var.set("All" if current_qtype is None else current_qtype)

        current_completed = self._resolve_completed_flag()
        if current_completed is None:
            self.completed_var.set("All")
        elif current_completed is True:
            self.completed_var.set("Completed")
        else:
            self.completed_var.set("Incomplete")

    def _apply_selected_menu_value(self, menu, value):
        if menu is self.paper_menu:
            self.paper_var.set(value if value is not None else "All")
        elif menu is self.topic_menu:
            self.topic_var.set(value if value is not None else "All")
        elif menu is self.qtype_menu:
            self.qtype_var.set(value if value is not None else "All")
        elif menu is self.completed_menu:
            if value is None:
                self.completed_var.set("All")
            elif value is True:
                self.completed_var.set("Completed")
            else:
                self.completed_var.set("Incomplete")
        self.refresh_pool()

    def refresh_pool(self):
        paper = self._resolve_filter_value(self.paper_var.get())
        topic = self._resolve_filter_value(self.topic_var.get())
        q_type = self._resolve_filter_value(self.qtype_var.get())
        completed = self._resolve_completed_flag()

        pool = self.app.get_question_pool(
            paper=paper,
            topic=topic,
            q_type=q_type,
            completed=completed,
        )

        self._refresh_filter_option_counts()
        self.pool_count_label.config(text=f"{len(pool)} questions")

        self.pool_listbox.delete(0, tk.END)
        if not pool:
            self.pool_listbox.insert(tk.END, "No questions match the selected filters")
            self.selected_key = None
            return

        for key in pool:
            self.pool_listbox.insert(tk.END, key)

        self.selected_key = random.choice(pool)
        self.pool_listbox.selection_clear(0, tk.END)
        self.pool_listbox.selection_set(0)

    def _select_pool_item(self, event=None):
        selected = self.pool_listbox.curselection()
        if not selected:
            return

        item = self.pool_listbox.get(selected[0])
        if item == "No questions match the selected filters":
            self.selected_key = None
            return

        self.selected_key = item

    def select_pool(self):
        self.app.set_active_pool_filters(
            paper=self._resolve_filter_value(self.paper_var.get()),
            topic=self._resolve_filter_value(self.topic_var.get()),
            q_type=self._resolve_filter_value(self.qtype_var.get()),
            completed=self._resolve_completed_flag(),
        )
        self.destroy()

    def _load_selected_question(self):
        if not self.selected_key:
            messagebox.showinfo("No question selected", "Choose a question from the pool first.")
            return

        self.app.current_session = self.app.open_question(self.selected_key)
        self.app.save_session_progress()
        self.destroy()


class FinishForm(tk.Toplevel):
    """Single-page finish form for score, remarks, and topic entry."""

    def __init__(self, parent, all_topics):
        super().__init__(parent)
        self.title("Finish question")
        self.geometry("500x560")
        self.transient(parent)
        self.grab_set()

        self.result = {"score": None, "remarks": "", "topic": None}
        self.all_topics = sorted(all_topics or [])

        tk.Label(self, text="Finish question", font=("Arial", 14, "bold")).pack(pady=(16, 10))

        tk.Label(self, text="Score %:", font=("Arial", 10, "bold")).pack(anchor="w", padx=16)
        self.score_var = tk.StringVar(value="0")
        self.score_entry = tk.Entry(self, textvariable=self.score_var, font=("Arial", 12))
        self.score_entry.pack(fill="x", padx=16, pady=(4, 12))

        tk.Label(self, text="Remarks:", font=("Arial", 10, "bold")).pack(anchor="w", padx=16)
        self.remarks_text = tk.Text(self, height=6, font=("Arial", 10))
        self.remarks_text.pack(fill="both", padx=16, pady=(4, 12))

        tk.Label(self, text="Topic:", font=("Arial", 10, "bold")).pack(anchor="w", padx=16)
        self.topic_var = tk.StringVar()
        self.topic_entry = tk.Entry(self, textvariable=self.topic_var, font=("Arial", 11))
        self.topic_entry.pack(fill="x", padx=16, pady=(4, 4))
        self.topic_entry.bind("<KeyRelease>", self._filter_topics)

        self.topic_listbox = tk.Listbox(self, height=6, exportselection=False, font=("Arial", 10))
        self.topic_listbox.pack(fill="x", padx=16, pady=(0, 10))
        self.topic_listbox.bind("<<ListboxSelect>>", self._select_topic)
        self._render_topics(self.all_topics)

        button_row = tk.Frame(self)
        button_row.pack(fill="x", padx=16, pady=(0, 16))
        tk.Button(button_row, text="Save attempt", command=self._submit, width=14).pack(side="right")
        tk.Button(button_row, text="Cancel", command=self.destroy, width=12).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window(self)

    def _render_topics(self, topics):
        self.topic_listbox.delete(0, tk.END)
        if not topics:
            self.topic_listbox.insert(tk.END, "No matching topics")
            return

        for topic in topics:
            self.topic_listbox.insert(tk.END, topic)

    def _filter_topics(self, event=None):
        typed = self.topic_var.get().strip().lower()
        if not typed:
            filtered = self.all_topics
        else:
            filtered = [topic for topic in self.all_topics if typed in topic.lower()]
        self._render_topics(filtered)

    def _select_topic(self, event=None):
        selected = self.topic_listbox.curselection()
        if not selected:
            return
        item = self.topic_listbox.get(selected[0])
        if item == "No matching topics":
            return
        self.topic_var.set(item)
        self.topic_entry.icursor(tk.END)

    def _cancel(self):
        self.result = {"score": None, "remarks": "", "topic": None}
        self.destroy()

    def _submit(self):
        try:
            score_text = self.score_var.get().strip()
            score = float(score_text) if score_text else 0.0
            if score < 0 or score > 100:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid score", "Score must be a number between 0 and 100.")
            return

        remarks = self.remarks_text.get("1.0", tk.END).strip()
        topic = self.topic_var.get().strip() or None

        self.result = {
            "score": score,
            "remarks": remarks,
            "topic": topic,
        }
        self.destroy()


class PastPaperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Past Paper App")
        self.root.geometry("520x260")
        self.root.minsize(420, 220)

        self.app = PastPaperApp(question_dir="QP_split")
        self.after_id = None
        self._timer_toggle_lock = False
        self._timer_started = False

        self.question_label = tk.Label(root, text="", font=("Arial", 11, "bold"), fg="darkblue")
        self.question_label.pack(pady=(18, 8), anchor="center")

        self.timer_var = tk.StringVar(value="Paused 00:00")
        self.timer_button = tk.Button(
            root,
            textvariable=self.timer_var,
            width=16,
            height=2,
            font=("Arial", 24, "bold"),
            bg="#e8f0fe",
            fg="#1a1a1a",
        )
        self.timer_button.bind("<Button-1>", self.on_timer_click)
        self.timer_button.pack(pady=8)

        self.select_question_button = tk.Label(
            root,
            text="Question selector",
            fg="blue",
            cursor="hand2",
            font=("Arial", 11, "underline"),
        )
        self.select_question_button.bind("<Button-1>", lambda event: self.open_question_selector())
        self.select_question_button.pack(pady=(0, 8))

        self.finish_button = tk.Button(
            root,
            text="Finish",
            command=self.finish_session,
            width=18,
            height=2,
            bg="#d9534f",
            fg="white",
            font=("Arial", 11, "bold"),
        )
        self.finish_button.pack(pady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(root, textvariable=self.status_var, fg="darkgreen", font=("Arial", 10))
        self.status_label.pack(pady=(4, 0))

        self.refresh_view()
        self.update_timer()

    def _format_elapsed(self, seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        minutes, secs = divmod(total_seconds, 60)
        return f"{minutes:02d}:{secs:02d}"

    def open_question_pdf(self):
        session = self.app.current_session
        if session is None:
            messagebox.showinfo("No question", "No question is currently open.")
            return

        pdf_path = session.question_pdf
        if not pdf_path or not pdf_path.exists():
            messagebox.showinfo("Question not found", f"Question PDF does not exist: {pdf_path}")
            return

        try:
            os.startfile(str(pdf_path))
        except OSError:
            messagebox.showinfo("Open file", f"Open this file manually: {pdf_path}")

    def on_timer_click(self, event=None):
        if self._timer_toggle_lock:
            return "break"

        if self.app.current_session is None:
            messagebox.showinfo("No question", "Open a question first.")
            return "break"

        self._timer_toggle_lock = True
        self.root.after(250, lambda: setattr(self, "_timer_toggle_lock", False))

        session = self.app.current_session
        try:
            if session.started and not session.is_paused:
                self.app.pause_timer()
            elif session.is_paused:
                self.app.resume_timer()
            else:
                self.app.start_timer()
        except ValueError:
            messagebox.showinfo("No question", "Open a question first.")
            return "break"

        self._timer_started = True
        self.refresh_view()
        return "break"

    def refresh_view(self):
        session = self.app.current_session
        if session is None:
            self.question_label.config(text="No question loaded")
            self.timer_var.set("Paused 00:00")
            return

        question_name = session.question_key
        self.question_label.config(text=question_name)
        self.question_label.bind("<Button-1>", lambda event: self.open_question_pdf())
        self.question_label.bind("<Button-2>", lambda event: self.open_question_pdf())
        self.question_label.bind("<Button-3>", lambda event: self.open_question_pdf())

        if session.started and not session.is_paused:
            self.timer_var.set(f"Running {self._format_elapsed(session.current_elapsed_seconds)}")
        else:
            self.timer_var.set(f"Paused {self._format_elapsed(session.current_elapsed_seconds)}")

    def update_timer(self):
        session = self.app.current_session
        if session is not None:
            elapsed = self._format_elapsed(session.current_elapsed_seconds)
            if session.started and not session.is_paused:
                self.timer_var.set(f"Running {elapsed}")
                self.app.save_session_progress()
            else:
                self.timer_var.set(f"Paused {elapsed}")
                self.app.save_session_progress()
        else:
            self.timer_var.set("Paused 00:00")

        self.after_id = self.root.after(250, self.update_timer)

    def on_close(self):
        self.app.save_session_progress()
        self.root.destroy()

    def open_question_selector(self):
        QuestionSelectorDialog(self.root, self.app)
        self.refresh_view()

    def finish_session(self):
        # This is the user-facing finish flow. It opens the crib, asks for score and
        # remarks, saves the attempt, and then routes into the next question logic.
        if self.app.current_session is None:
            messagebox.showinfo("No question", "Open a question first.")
            return

        try:
            self.app.finish_question()
        except ValueError:
            messagebox.showinfo("No question", "Open a question first.")
            return

        crib_path = self.app.find_solution_pdf(self.app.current_session.question_key)
        if crib_path:
            try:
                os.startfile(str(crib_path))
                self.status_var.set(f"CRIB opened: {crib_path}")
            except OSError:
                self.status_var.set(f"CRIB file available: {crib_path}")
        else:
            self.status_var.set("CRIB not found.")

        form = FinishForm(self.root, self.app.store.get_all_topics())
        if form.result["score"] is None:
            self.refresh_view()
            return

        score = form.result["score"]
        remarks = form.result["remarks"]
        topic = form.result["topic"]

        result = self.app.submit_attempt(score, remarks, topic=topic)
        self.status_var.set(f"Saved: {result['question']}")
        messagebox.showinfo(
            "Attempt saved",
            f"Saved attempt for {result['question']}\nNext question: {result['next_question']}",
        )
        self.refresh_view()


def main():
    root = tk.Tk()
    app = PastPaperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
