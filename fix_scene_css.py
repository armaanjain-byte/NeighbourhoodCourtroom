import os
import re

def fix_contrast_and_empty():
    with open('ui/components/courtroom_scene.py', 'r', encoding='utf-8') as f:
        text = f.read()

    # Opacity fixes
    text = re.sub(r'(details\.bubble-detail summary\s*{[^}]+?opacity:\s*)0\.55', r'\g<1>0.85', text)
    text = re.sub(r'(\.detail-body\s*{[^}]+?opacity:\s*)0\.7', r'\g<1>0.85', text)
    text = re.sub(r'(\.evidence-list\s*{[^}]+?opacity:\s*)0\.6', r'\g<1>0.85', text)
    text = re.sub(r'(\.bubble-objection \.obj-claim\s*{[^}]+?opacity:\s*)0\.8', r'\g<1>0.85', text)
    text = re.sub(r'(\.thinking-indicator\s*{[^}]+?opacity:\s*)0\.45', r'\g<1>0.85', text)
    text = re.sub(r'(\.thinking-strip\s*{[^}]+?opacity:\s*)0\.35', r'\g<1>0.85', text)
    text = text.replace('<span style="opacity:0.7">', '<span style="opacity:0.9">')

    # Add empty state CSS for live feed (agent-feed)
    empty_live_css = """
.agent-feed:empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 2px dashed rgba(18, 18, 18, 0.4);
    opacity: 0.8;
    margin-top: 1rem;
    min-height: 100px;
}
.agent-feed:empty::after {
    content: "AWAITING STATEMENT...";
    font-family: 'Outfit', sans-serif;
    font-weight: 900;
    font-size: 0.75rem;
    letter-spacing: 0.1em;
    color: rgba(18, 18, 18, 0.6);
}
"""
    if empty_live_css not in text:
        text = text.replace('.agent-feed {\n    flex: 1;', empty_live_css.lstrip() + '\n.agent-feed {\n    flex: 1;')

    # Add empty state CSS for cinematic feed (content-[agent])
    empty_cinematic_css = """
div[id^="content-"]:empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 2px dashed currentColor;
    opacity: 0.6;
    margin-top: 1rem;
    min-height: 100px;
}
div[id^="content-"]:empty::after {
    content: "AWAITING STATEMENT...";
    font-family: 'Outfit', sans-serif;
    font-weight: 900;
    font-size: 0.8rem;
    letter-spacing: 0.1em;
    color: currentColor;
}
"""
    if empty_cinematic_css not in text:
        text = text.replace('details > summary::-webkit-details-marker { display: none; }', 'details > summary::-webkit-details-marker { display: none; }\n' + empty_cinematic_css)

    with open('ui/components/courtroom_scene.py', 'w', encoding='utf-8') as f:
        f.write(text)

if __name__ == '__main__':
    fix_contrast_and_empty()
    print("Done")
