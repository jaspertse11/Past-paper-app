"""PDF splitting utilities for turning one paper into per-question PDFs.

This module scans a source exam paper for question markers such as "1 (short)"
and writes each question to its own PDF in the QP_split folder. The resulting
individual question files are then used by the GUI and JSON store.
"""

import os
import re
from pathlib import Path

import pymupdf


def split_pdf_by_questions(input_pdf_path, output_dir="QP_split"):
    # 1. Open the source PDF document
    input_pdf_path = Path(input_pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    doc = pymupdf.open(str(input_pdf_path))
    original_name = os.path.splitext(input_pdf_path.name)[0]

    if input_pdf_path.parent.name.lower() == "qp" and input_pdf_path.parent.parent.name.lower().startswith("1p"):
        source_folder_name = input_pdf_path.parent.parent.name
    else:
        source_folder_name = input_pdf_path.parent.name

    question_starts = []  # Stores tuples of (question_number, question_type, start_page_index)

    # 2. Pattern matching question headers like "1 (short)", "2 (long)", "10 (short)"
    question_pattern = re.compile(r'(?:^|\n)\s*(\d+)\s*\((short|long)\)', re.IGNORECASE)

    # 3. Scan each page text to record every question start on that page
    for page_num in range(len(doc)):
        text = doc[page_num].get_text("text")
        matches = list(question_pattern.finditer(text))

        for match in matches:
            q_num = match.group(1)
            q_type = match.group(2).lower()
            # Ensure each question is registered only at its initial appearance.
            # Keep the numeric value as an int so the ordering is by actual question number,
            # not by the text label "short" or "long".
            if not any(q[0] == int(q_num) for q in question_starts):
                question_starts.append((int(q_num), q_type, page_num))

    # 4. Sort detected questions by document order: page number first, then question number.
    # Sorting by q_type was the reason "short" questions were grouped incorrectly.
    question_starts.sort(key=lambda x: (x[2], x[0]))

    if not question_starts:
        print(f"No question markers found in: {input_pdf_path.name}")

    # 5. Extract page ranges for each question into separate PDF files.
    # If multiple questions start on the same page, keep that same page as the range
    # instead of collapsing them into one combined range.
    for i in range(len(question_starts)):
        q_num, q_type, start_page = question_starts[i]

        if i + 1 < len(question_starts):
            next_page = question_starts[i + 1][2]
            if next_page == start_page:
                end_page = start_page
            else:
                end_page = next_page - 1
        else:
            end_page = len(doc) - 1

        # Create a clean target PDF and copy over vector graphics, images, and text
        new_doc = pymupdf.open()
        new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)

        output_filename = output_dir / f"{original_name}_{source_folder_name}_{q_num}_{q_type}.pdf"
        new_doc.save(str(output_filename))
        new_doc.close()

        print(f"Exported Question {q_num} ({q_type}): Pages {start_page + 1} to {end_page + 1} -> {output_filename}")

    doc.close()
    return len(question_starts)


def split_all_pdfs_in_folder(source_folder="QP_full", output_folder="QP_split"):
    # 1. Look through every PDF in the source folder
    source_dir = Path(source_folder)
    output_dir = Path(output_folder)
    output_dir.mkdir(exist_ok=True)

    processed_count = 0
    split_count = 0
    pdf_files = sorted(source_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDFs found in: {source_dir}")

    # 2. Process every PDF file one by one
    for pdf_path in pdf_files:
        print(f"Processing: {pdf_path.name}")
        processed_count += 1
        split_count += split_pdf_by_questions(pdf_path, output_dir=output_dir)

    print(f"\nSummary: {processed_count} PDF(s) processed; {split_count} question PDF(s) created.")
    return processed_count, split_count


# Run the splitter across all PDFs in the source folders
if __name__ == "__main__":
    base_dir = Path(r"C:\Users\jaspe\Desktop\past paper app")
    output_dir = base_dir / "QP_split"
    output_dir.mkdir(exist_ok=True)

    total_processed = 0
    total_split = 0
    checked_years = []

    for paper_dir in sorted(base_dir.glob("1P*")):
        qp_dir = paper_dir / "QP"
        checked_years.append(paper_dir.name)
        if qp_dir.exists():
            print(f"\nChecking {paper_dir.name} / QP")
            processed, split = split_all_pdfs_in_folder(str(qp_dir), str(output_dir))
            total_processed += processed
            total_split += split
        else:
            print(f"No QP folder found for: {paper_dir.name}")

    print(f"\nChecked year folders: {checked_years}")
    print(f"FINAL SUMMARY: {total_processed} PDF(s) processed across all year folders; {total_split} question PDF(s) created in {output_dir}.")
