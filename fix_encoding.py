import os

def fix_transcript():
    with open('ui/components/transcript_view.py', 'r', encoding='utf-8') as f:
        text = f.read()
        
    try:
        fixed_text = text.encode('latin1').decode('utf-8')
    except Exception as e:
        print("Failed latin1 decode:", e)
        # Try windows-1252 but ignore errors
        fixed_text = text.encode('cp1252', errors='replace').decode('utf-8', errors='replace')
        
    fixed_text = fixed_text.replace("'s claim:", "'s claim that:")
    
    with open('ui/components/transcript_view.py', 'w', encoding='utf-8') as f:
        f.write(fixed_text)
    
if __name__ == '__main__':
    fix_transcript()
    print("Fixed!")
