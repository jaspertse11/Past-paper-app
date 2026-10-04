"""Earlier draft used for experimenting with PDF splitting logic.

This script is not the active app logic; it is a simpler prototype for testing
how a PDF can be split into question-level PDFs based on question markers.
"""

import pymupdf
import re
import os

def split_pdf_by_questions(input_pdf_path):
    # 1. Open the source PDF document
    doc = pymupdf.open(input_pdf_path)
    original_name = os.path.splitext(os.path.basename(input_pdf_path))[0]
    question_starts = []  # Stores tuples of (question_number, start_page_index)

    # 2. Pattern matching question headers like "1 (short)", "2 (long)", "10 (short)"
    question_pattern = re.compile(r'(?:^|\n)\s*(\d+)\s*\((?:short|long)\)', re.IGNORECASE)

    # 3. Scan each page text to record where each question starts
    for page_num in range(len(doc)):
        text = doc[page_num].get_text("text")
        match = question_pattern.search(text)
        
        if match:
            q_num = match.group(1)
            # Ensure each question is registered only at its initial appearance
            if not any(q[0] == q_num for q in question_starts):
                question_starts.append((q_num, page_num))

    # 4. Sort detected questions sequentially by page order
    question_starts.sort(key=lambda x: x[1])

    # 5. Extract page ranges for each question into separate PDF files
    for i in range(len(question_starts)):
        q_num, start_page = question_starts[i]
        
        # End page is the page right before the next question starts, 
        # or the final page of the PDF for the last question
        if i + 1 < len(question_starts):
            end_page = question_starts[i + 1][1] - 1
        else:
            end_page = len(doc) - 1

        # Create a clean target PDF and copy over vector graphics, images, and text
        new_doc = pymupdf.open()
        new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
        
        output_filename = f"{original_name}_{q_num}.pdf"
        new_doc.save(output_filename)
        new_doc.close()
        
        print(f"Exported Question {q_num}: Pages {start_page + 1} to {end_page + 1} -> {output_filename}")

    doc.close()

# Run the splitter on your question paper
split_pdf_by_questions("QP_2025.pdf")